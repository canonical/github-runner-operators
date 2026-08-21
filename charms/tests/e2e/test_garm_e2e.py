# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""GARM end-to-end test on ProdStack."""

import logging
import time

import jubilant
import pytest
import requests

from tests.integration.conftest import _garm_login, _get_garm_address
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
    ref = required_env("GITHUB_REF_NAME")

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
        poll_interval=15,
        timeout=45 * 60,
    )

    assert conclusion == "success", (
        f"Workflow run {run_id} concluded as '{conclusion}', expected 'success'"
    )
    logger.info("GARM E2E test passed: workflow run %s concluded as 'success'", run_id)


def _wait_for_runner_online(
    juju: jubilant.Juju,
    garm_app: str,
    scaleset_name: str,
    timeout: int = 15 * 60,
    poll_interval: int = 15,
) -> None:
    """Block until the named scale set has a runner GitHub has registered.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        scaleset_name: Name of the scale set whose runners to wait for.
        timeout: Seconds to wait before failing the test.
        poll_interval: Seconds between polls.
    """
    address = _get_garm_address(juju, garm_app)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    token = _garm_login(juju, address)
    deadline = time.time() + timeout
    logger.info("Waiting for a registered runner in scale set %r", scaleset_name)

    while time.time() < deadline:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            scalesets = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
            if scalesets.status_code == 401:
                # The poll window outlives the JWT; renew and retry on the next pass.
                token = _garm_login(juju, address)
                time.sleep(poll_interval)
                continue
            scalesets.raise_for_status()
            scaleset = next(
                (s for s in scalesets.json() or [] if s.get("name") == scaleset_name), None
            )
            if scaleset is not None:
                instances = requests.get(
                    f"{base_url}/scalesets/{scaleset['id']}/instances",
                    headers=headers,
                    timeout=30,
                )
                instances.raise_for_status()
                for instance in instances.json() or []:
                    if instance.get("runner_status") in REGISTERED_RUNNER_STATUSES:
                        logger.info(
                            "Runner %s registered (runner_status=%s)",
                            instance.get("name"),
                            instance.get("runner_status"),
                        )
                        return
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Transient error polling GARM, retrying: %s", exc)

        time.sleep(poll_interval)

    pytest.fail(
        f"No runner in scale set {scaleset_name!r} reached a registered state "
        f"({' or '.join(REGISTERED_RUNNER_STATUSES)}) within {timeout}s."
    )
