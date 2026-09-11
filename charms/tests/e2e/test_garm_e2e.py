# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""GARM end-to-end tests on ProdStack."""

import logging
import os

import jubilant
import pytest
import requests
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_delay,
    wait_fixed,
)
from tests.e2e.openstack import wait_for_server_state
from tests.integration.conftest import (
    _collect_debug_info,
    _garm_login,
    _get_garm_address,
)
from tests.integration.helpers import (
    E2E_APP_ENV,
    GITHUB_REPOSITORY_ENV_VAR,
    create_github_app_client,
    dispatch_workflow,
    required_env,
    wait_for_completion,
)

logger = logging.getLogger(__name__)

WORKFLOW_PATH = ".github/workflows/garm_e2e_test_run.yaml"
GARM_API_PORT = 8080

# GARM tracks two independent lifecycles. `status` is the provider's view -- the VM
# exists and is running -- which is reached well before the agent inside it has
# registered. Only `runner_status` reflects GitHub having seen the runner, so it is
# what a dispatch can safely follow; `pending` is registered-but-not-yet-usable.
# Values from params.RunnerStatus in GARM.
REGISTERED_RUNNER_STATUSES = ("idle", "active")

# Timeout and cadence constants for the tenacity-backed waits below.
RUNNER_REGISTRATION_TIMEOUT = 25 * 60
RUNNER_POLL_INTERVAL = 15
WORKFLOW_COMPLETION_TIMEOUT = 45 * 60
REMOVAL_SERVER_PRESENT_TIMEOUT = 2 * 60
REMOVAL_SERVER_ABSENT_TIMEOUT = 10 * 60
REMOVAL_APP_REMOVED_TIMEOUT = 15 * 60
GARM_HTTP_TIMEOUT = 30

# The poll windows outlive the admin JWT, so the token is cached per GARM
# address and only refreshed once the API answers 401.
GARM_TOKEN_CACHE: dict[str, str] = {}
LAST_INSTANCE_SUMMARIES: dict[str, list[str]] = {}


def _garm_headers(juju: jubilant.Juju, address: str) -> dict[str, str]:
    """Authorization headers, logging in once per address and caching the JWT."""
    token = GARM_TOKEN_CACHE.get(address)
    if token is None:
        token = _garm_login(juju, address)
        GARM_TOKEN_CACHE[address] = token
    return {"Authorization": f"Bearer {token}"}


def _scaleset_by_label(
    base_url: str, headers: dict[str, str], runner_label: str
) -> dict | None:
    """Return the enabled scale set tagged with the label, or None.

    The charm adds a hash to scale-set names, so the unique routing label is
    the only stable handle; disabled generations being drained are excluded.
    """
    response = requests.get(
        f"{base_url}/scalesets", headers=headers, timeout=GARM_HTTP_TIMEOUT
    )
    response.raise_for_status()
    return next(
        (
            scaleset
            for scaleset in response.json() or []
            if scaleset.get("enabled") is True
            and any(
                tag.get("name") == runner_label for tag in scaleset.get("tags") or []
            )
        ),
        None,
    )


class _RunnerNotRegistered(Exception):
    """Raised between polls until an instance reaches a registered state.

    Carries the last observed instances so the failure report can say which
    stage stalled instead of "nothing ever spawned."
    """

    def __init__(self, instances: list[dict]) -> None:
        super().__init__("no registered runner observed yet")
        self.instances = instances


def _log_instances_on_change(runner_label: str, instances: list[dict]) -> None:
    """Log the instance list only when it changes, so the poll trail stays short."""
    summary = sorted(
        f"{i.get('name')}: status={i.get('status')} "
        f"runner_status={i.get('runner_status')}"
        for i in instances
    )
    if summary != LAST_INSTANCE_SUMMARIES.get(runner_label):
        LAST_INSTANCE_SUMMARIES[runner_label] = summary
        logger.info("Scale set instances: %s", summary)


def _registered_runner(juju: jubilant.Juju, garm_app: str, runner_label: str) -> dict:
    """One poll: return a registered runner in the label's scale set.

    Raises _RunnerNotRegistered when the state is not reached, which the
    tenacity retry in _wait_for_runner_online turns into another poll.
    """
    address = _get_garm_address(juju, garm_app)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = _garm_headers(juju, address)
    scaleset = _scaleset_by_label(base_url, headers, runner_label)
    if scaleset is None:
        raise _RunnerNotRegistered([])
    response = requests.get(
        f"{base_url}/scalesets/{scaleset['id']}/instances",
        headers=headers,
        timeout=GARM_HTTP_TIMEOUT,
    )
    if response.status_code == 401:
        # The old JWT died mid-window; the next poll logs in again.
        GARM_TOKEN_CACHE.pop(address, None)
        raise _RunnerNotRegistered([])
    response.raise_for_status()
    instances = response.json() or []
    _log_instances_on_change(runner_label, instances)
    for instance in instances:
        if instance.get("runner_status") in REGISTERED_RUNNER_STATUSES:
            logger.info(
                "Runner %s registered (runner_status=%s)",
                instance.get("name"),
                instance.get("runner_status"),
            )
            return instance
    raise _RunnerNotRegistered(instances)


def test_garm_e2e(juju: jubilant.Juju, garm_with_ingress: str, e2e_scaleset: str):
    """
    arrange: GARM deployed with postgresql + traefik ingress; garm-configurator holding real
        ProdStack credentials, a stable runner-image name, and a unique run label;
        GARM's controller metadata_url resolved to the routable LB address.
    act: Dispatch garm_e2e_test_run.yaml against the run label and wait for completion.
    assert: The workflow run concludes 'success' — which is only reachable if GARM
        authenticated to OpenStack, booted a VM on the published image, the runner
        registered with GitHub, picked up the job, and exited clean.
    """
    repo_path = required_env(GITHUB_REPOSITORY_ENV_VAR)
    label = e2e_scaleset  # Unique runner label returned by e2e_scaleset fixture
    # workflow_dispatch resolves only branches and tags, never PR refs: under
    # the pull_request event GITHUB_REF_NAME is "N/merge", which the dispatch
    # API answers with 422 "No ref found". The PR's head branch carries the
    # same workflow file and is dispatchable; a workflow_dispatch run of this
    # suite has no head ref, and GITHUB_REF_NAME is already a branch there.
    ref = os.environ.get("GITHUB_HEAD_REF") or required_env("GITHUB_REF_NAME")

    # Wait for runner VM to spawn and register before dispatching
    _wait_for_runner_online(juju, garm_with_ingress, label)

    github_client = create_github_app_client(E2E_APP_ENV)

    logger.info("Dispatching %s on %s with label %s", WORKFLOW_PATH, ref, label)
    run_id = dispatch_workflow(
        github_client=github_client,
        repo_path=repo_path,
        workflow_path=WORKFLOW_PATH,
        ref=ref,
        inputs={"runner-label": label},
    )

    logger.info("Workflow run %d dispatched, waiting for completion", run_id)
    # Longer than garm_e2e_test_run.yaml's own timeout-minutes, so a wedged runner
    # surfaces as that job timing out -- which names the step that hung -- rather than
    # as this wait expiring first and reporting only that nothing finished. It also has
    # to cover queue time: the job does not start until a VM has booted and registered,
    # and timeout-minutes does not span that.
    conclusion = wait_for_completion(
        github_client=github_client,
        repo_path=repo_path,
        run_id=run_id,
        poll_interval=RUNNER_POLL_INTERVAL,
        timeout=WORKFLOW_COMPLETION_TIMEOUT,
    )

    assert conclusion == "success", (
        f"Workflow run {run_id} concluded as '{conclusion}', expected 'success'"
    )
    logger.info("GARM E2E test passed: workflow run %s concluded as 'success'", run_id)


def _wait_for_runner_online(
    juju: jubilant.Juju,
    garm_app: str,
    runner_label: str,
    timeout: int = RUNNER_REGISTRATION_TIMEOUT,
    poll_interval: int = RUNNER_POLL_INTERVAL,
) -> None:
    """Block until a scale set serving the label has a registered runner.

    Tenacity polls _registered_runner every ``poll_interval`` seconds until
    ``timeout`` elapses; _RunnerNotRegistered (with the last observed
    instances) carries the diagnostics for the failure report.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        runner_label: Unique runner label configured by the E2E fixture.
        timeout: Seconds to wait before failing the test.
        poll_interval: Seconds between polls.
    """
    # Must outlast GARM's own runner bootstrap timeout -- 20 minutes by default,
    # and not configurable through garm-configurator. Waiting less fails the test
    # on a runner GARM still considers booting, instead of letting GARM reap a
    # stuck one and spawn a replacement.
    logger.info("Waiting for a registered runner serving label %r", runner_label)
    try:
        Retrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(poll_interval),
            retry=retry_if_exception_type(
                (
                    _RunnerNotRegistered,
                    requests.RequestException,
                    ValueError,
                    KeyError,
                )
            ),
            reraise=True,
        )(_registered_runner, juju, garm_app, runner_label)
    except _RunnerNotRegistered as exc:
        # Leave the evidence in the log before failing: the instance state says
        # which stage stalled, since GARM only reaches "registered" after spawning
        # an instance, booting its VM, and installing the runner against the
        # callback URL. An empty last observation means no instance was found for
        # the label; pending_create means the provider never picked one up;
        # running with a pending runner_status means the VM booted but its
        # bootstrap never called back, with GARM's own logs -- collected next,
        # through the sentinel redactor -- carrying the reason.
        if exc.instances:
            logger.error(
                "Last instances observed for runner label %s (possibly reaped by "
                "GARM's bootstrap-timeout reaper by now): %s",
                runner_label,
                sorted(
                    f"{i.get('name')}: status={i.get('status')} "
                    f"runner_status={i.get('runner_status')} "
                    f"provider_id={i.get('provider_id')!r}"
                    for i in exc.instances
                ),
            )
        else:
            logger.error(
                "No instance was ever observed for runner label %s", runner_label
            )
        _collect_debug_info(juju, garm_app)
        pytest.fail(
            f"No runner serving label {runner_label!r} reached a registered state "
            f"({' or '.join(REGISTERED_RUNNER_STATUSES)}) within {timeout}s."
        )


class _InstanceNotRunning(Exception):
    """Raised between polls until an instance reaches provider status running.

    Carries the last observed instances for the failure report.
    """

    def __init__(self, instances: list[dict]) -> None:
        super().__init__("no provider-running instance observed yet")
        self.instances = instances


def _running_instance(juju: jubilant.Juju, garm_app: str, runner_label: str) -> dict:
    """One poll: return a provider-running instance in the label's scale set.

    Raises _InstanceNotRunning until one is observed, which the tenacity retry
    in _wait_for_provider_running_instance turns into another poll.
    """
    address = _get_garm_address(juju, garm_app)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = _garm_headers(juju, address)
    scaleset = _scaleset_by_label(base_url, headers, runner_label)
    if scaleset is None:
        raise _InstanceNotRunning([])
    response = requests.get(
        f"{base_url}/scalesets/{scaleset['id']}/instances",
        headers=headers,
        timeout=GARM_HTTP_TIMEOUT,
    )
    if response.status_code == 401:
        # The old JWT died mid-window; the next poll logs in again.
        GARM_TOKEN_CACHE.pop(address, None)
        raise _InstanceNotRunning([])
    response.raise_for_status()
    instances = response.json() or []
    for instance in instances:
        if instance.get("status") == "running":
            logger.info(
                "Observed provider-running GARM instance %s (runner_status=%s)",
                instance.get("name"),
                instance.get("runner_status"),
            )
            return instance
    raise _InstanceNotRunning(instances)


def _wait_for_provider_running_instance(
    juju: jubilant.Juju,
    garm_app: str,
    runner_label: str,
    timeout: int = RUNNER_REGISTRATION_TIMEOUT,
    poll_interval: int = RUNNER_POLL_INTERVAL,
) -> dict:
    """Wait for the GARM provider to report one real runner instance as running.

    Tenacity polls _running_instance every ``poll_interval`` seconds until
    ``timeout`` elapses; _InstanceNotRunning (with the last observed instances)
    carries the diagnostics for the failure report.
    """
    last_instances: list[dict] = []
    try:
        return Retrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(poll_interval),
            retry=retry_if_exception_type(
                (
                    _InstanceNotRunning,
                    requests.RequestException,
                    ValueError,
                    KeyError,
                )
            ),
            reraise=True,
        )(_running_instance, juju, garm_app, runner_label)
    except _InstanceNotRunning as exc:
        last_instances = exc.instances
        pytest.fail(
            f"No provider-running instance appeared in {runner_label!r}; "
            f"last observed instances: {last_instances!r}"
        )


def test_garm_charm_removal_drains_provider_runner(
    juju: jubilant.Juju,
    garm_with_ingress: str,
    e2e_scaleset: str,
    openstack_credentials: dict[str, str],
) -> None:
    """Remove GARM normally and verify its live runner is removed from Nova.

    Runs after ``test_garm_e2e`` in the same deployed topology, so the runner
    observed here is the one that just served the dispatched job.
    """
    instance = _wait_for_provider_running_instance(
        juju, garm_with_ingress, e2e_scaleset
    )
    server_name = instance.get("name")
    assert server_name, f"GARM instance did not include a provider name: {instance!r}"

    wait_for_server_state(
        openstack_credentials,
        server_name,
        present=True,
        timeout=REMOVAL_SERVER_PRESENT_TIMEOUT,
    )

    logger.info("Removing disposable GARM application through the normal Juju path")
    juju.remove_application(garm_with_ingress)
    juju.wait(
        lambda status: garm_with_ingress not in status.apps,
        timeout=REMOVAL_APP_REMOVED_TIMEOUT,
        delay=10,
    )

    wait_for_server_state(
        openstack_credentials,
        server_name,
        present=False,
        timeout=REMOVAL_SERVER_ABSENT_TIMEOUT,
    )
