# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""GARM end-to-end test on ProdStack."""

import logging
import os
import pty
import re
import select
import subprocess
import time
import uuid

import jubilant
import pytest
import requests
from tests.e2e.conftest import GarmCli
from tests.integration.conftest import (
    _collect_debug_info,
    _credential_sentinels,
    _garm_login,
    _get_garm_address,
    _redact_sentinels,
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
# Terminal: GARM reaps the VM shortly after marking a runner failed, so anything
# that needs the instance itself has to happen on the poll that first sees this.
FAILED_RUNNER_STATUS = "failed"

# CSI and OSC sequences: garm-cli drives a raw terminal, so the transcript is
# interleaved with colour, cursor and window-title control codes.
ANSI_PATTERN = re.compile(
    r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|[\x00\x07]"
)

# How long a shell session must stay silent before it counts as ready for the
# next line typed at it. Generous, because every keystroke and every byte of
# output crosses two websocket hops -- the client to GARM, and GARM to the agent.
SHELL_QUIET_PERIOD = 2.0


# Deliberately ahead of test_garm_e2e: it reuses the idle runner the scale set
# already holds, whereas running it afterwards would wait for the ephemeral
# runner consumed by the workflow to be torn down and replaced.
def test_garm_agent_shell(
    juju: jubilant.Juju,
    garm_with_ingress: str,
    e2e_scaleset: str,
    garm_cli: GarmCli,
):
    """
    arrange: The E2E scale set deployed with enable-shell, holding a registered runner
        whose GARM agent has dialled back and advertised shell support. Skipped unless
        the ingress terminates TLS, without which the agent disables its own shell.
    act: Open `garm-cli runner shell` against that runner and run one command.
    assert: The command's expanded output comes back — reachable only if the
        rock-built agent the charm published to GARM is running on the VM, connected
        to the agent URL the charm derived from the ingress, and GARM relayed a PTY
        over that websocket in both directions.
    """
    _skip_unless_agent_url_is_tls(juju, garm_with_ingress)
    instance = _wait_for_runner_online(juju, garm_with_ingress, e2e_scaleset)
    runner_name = instance["name"]
    _wait_for_shell_capability(juju, garm_with_ingress, runner_name)
    # The terminal echoes the command as typed, so a plain marker would be found
    # in the transcript whether or not anything ran it. Only a real shell turns
    # $((6*7)) into 42, so the expanded form is what proves the session works.
    marker = f"garm-shell-{uuid.uuid4().hex[:8]}"
    transcript = _run_in_agent_shell(garm_cli, runner_name, f"echo {marker}_$((6*7))")

    assert f"{marker}_42" in transcript, (
        f"Expected the agent shell on {runner_name} to print {marker}_42, got: "
        f"{transcript!r}"
    )
    logger.info("Agent shell on %s executed a command successfully", runner_name)


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
        poll_interval=15,
        timeout=45 * 60,
    )

    assert conclusion == "success", (
        f"Workflow run {run_id} concluded as '{conclusion}', expected 'success'"
    )
    logger.info("GARM E2E test passed: workflow run %s concluded as 'success'", run_id)


def _skip_unless_agent_url_is_tls(juju: jubilant.Juju, garm_app: str) -> None:
    """Skip unless the deployment can serve an agent shell at all.

    garm-agent drops enable_shell whenever its server URL is cleartext -- it
    refuses to expose a shell in the clear -- so with a plain-http ingress no
    runner ever advertises the capability, and waiting for one would only burn
    the timeout and report a failure that is really a missing certificate.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
    """
    address = _get_garm_address(juju, garm_app)
    response = requests.get(
        f"http://{address}:{GARM_API_PORT}/api/v1/controller",
        headers={"Authorization": f"Bearer {_garm_login(juju, address)}"},
        timeout=30,
    )
    response.raise_for_status()
    agent_url = (response.json() or {}).get("agent_url") or ""
    if not agent_url.startswith(("https://", "wss://")):
        pytest.skip(
            f"GARM's agent_url is {agent_url!r}: garm-agent disables its shell over a "
            "cleartext transport, so the remote shell needs an ingress that terminates "
            "TLS and runner VMs that trust its CA."
        )


def _wait_for_runner_online(
    juju: jubilant.Juju,
    garm_app: str,
    runner_label: str,
    timeout: int = 25 * 60,
    poll_interval: int = 15,
) -> dict:
    """Block until a scale set serving the label has a registered runner.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        runner_label: Unique runner label configured by the E2E fixture.
        timeout: Seconds to wait before failing the test.
        poll_interval: Seconds between polls.

    Returns:
        The GARM instance record of the runner that registered.
    """
    # Must outlast GARM's own runner bootstrap timeout -- 20 minutes by default,
    # and not configurable through garm-configurator. Waiting less fails the test
    # on a runner GARM still considers booting, instead of letting GARM reap a
    # stuck one and spawn a replacement.
    address = _get_garm_address(juju, garm_app)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    token = _garm_login(juju, address)
    deadline = time.time() + timeout
    last_instances: list[dict] = []
    last_summary: list[str] | None = None
    consoles_logged: set[str] = set()
    logger.info("Waiting for a registered runner serving label %r", runner_label)

    while time.time() < deadline:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            scalesets = requests.get(
                f"{base_url}/scalesets", headers=headers, timeout=30
            )
            if scalesets.status_code == 401:
                # The poll window outlives the JWT; renew and retry on the next pass.
                token = _garm_login(juju, address)
                time.sleep(poll_interval)
                continue
            scalesets.raise_for_status()
            # The charm adds a label hash to scale-set names. Match the unique
            # routing label instead, excluding disabled generations being drained.
            scaleset = next(
                (
                    s
                    for s in scalesets.json() or []
                    if s.get("enabled") is True
                    and any(t.get("name") == runner_label for t in s.get("tags") or [])
                ),
                None,
            )
            if scaleset is not None:
                instances_response = requests.get(
                    f"{base_url}/scalesets/{scaleset['id']}/instances",
                    headers=headers,
                    timeout=30,
                )
                instances_response.raise_for_status()
                instances = instances_response.json() or []
                summary = sorted(
                    f"{i.get('name')}: status={i.get('status')} "
                    f"runner_status={i.get('runner_status')}"
                    for i in instances
                )
                if summary != last_summary:
                    # Log on change only: the wait spans many polls, and this trail
                    # is what shows whether instances are appearing, failing, or
                    # never being created at all.
                    last_summary = summary
                    logger.info("Scale set instances: %s", summary)
                if instances:
                    # Keep the last non-empty observation: GARM's reaper removes
                    # instances from the scale set when the bootstrap timeout
                    # fires, so the final poll can be empty even though a VM
                    # existed -- and reporting that as "never spawned" would
                    # point the investigation at the wrong stage entirely.
                    last_instances = instances
                newly_failed = [
                    i
                    for i in instances
                    if i.get("runner_status") == FAILED_RUNNER_STATUS
                    and i.get("name") not in consoles_logged
                ]
                if newly_failed:
                    _log_instance_diagnostics(base_url, token, newly_failed)
                    consoles_logged.update(str(i.get("name")) for i in newly_failed)
                for instance in instances:
                    if instance.get("runner_status") in REGISTERED_RUNNER_STATUSES:
                        logger.info(
                            "Runner %s registered (runner_status=%s)",
                            instance.get("name"),
                            instance.get("runner_status"),
                        )
                        return instance
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Transient error polling GARM, retrying: %s", exc)

        time.sleep(poll_interval)

    # Leave the evidence in the log before failing: the instance state says which
    # stage stalled, since GARM only reaches "registered" after spawning an
    # instance, booting its VM, and installing the runner against the callback
    # URL. An empty last observation means no instance was found for the label;
    # pending_create means the provider never picked one up; running with a
    # pending runner_status means the VM booted but its bootstrap never called
    # back, with GARM's own logs -- collected next, through the sentinel
    # redactor -- carrying the reason.
    if last_instances:
        logger.error(
            "Last instances observed for runner label %s (possibly reaped by GARM's "
            "bootstrap-timeout reaper by now): %s",
            runner_label,
            sorted(
                f"{i.get('name')}: status={i.get('status')} "
                f"runner_status={i.get('runner_status')} provider_id={i.get('provider_id')!r}"
                for i in last_instances
            ),
        )
    else:
        logger.error("No instance was ever observed for runner label %s", runner_label)
    _log_instance_diagnostics(base_url, token, last_instances)
    _collect_debug_info(juju, garm_app)
    pytest.fail(
        f"No runner serving label {runner_label!r} reached a registered state "
        f"({' or '.join(REGISTERED_RUNNER_STATUSES)}) within {timeout}s."
    )


def _log_instance_diagnostics(base_url: str, token: str, instances: list[dict]) -> None:
    """Log why each VM that failed to produce a runner gave up.

    Two complementary sources, because the interesting failures fall either side of
    the VM's ability to talk to GARM. The bootstrap reports each step it completes and
    the reason it aborts, and GARM keeps those per instance, so when the VM did reach
    GARM its own account of the failure is already recorded and exact. When it did not,
    the last status message is simply the last step that worked, and only the serial
    console says what happened after it.
    """
    for instance in instances:
        _log_instance_status_messages(base_url, token, instance)
    _log_instance_console(instances)


def _log_instance_status_messages(base_url: str, token: str, instance: dict) -> None:
    """Log the bootstrap's own status messages for one instance.

    Best effort: this runs on a path that has already failed, and the instance may
    have been reaped between the poll that saw it and this call, so a failure to
    fetch must not mask the real failure.
    """
    name = instance.get("name")
    try:
        response = requests.get(
            f"{base_url}/instances/{name}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()
        instance_detail = response.json() or {}
        messages = instance_detail.get("status_messages") or []
    except (requests.RequestException, ValueError) as exc:
        logger.error("Could not read the status messages of %s: %s", name, exc)
        return
    # Set only when the IaaS itself refused the instance -- a missing image, an
    # exhausted quota -- which never reaches the bootstrap and so leaves no status
    # message at all.
    provider_fault = instance_detail.get("provider_fault")
    if provider_fault:
        logger.error("Provider fault for %s: %s", name, provider_fault)
    logger.error(
        "=== Bootstrap status messages for %s ===\n%s",
        name,
        "\n".join(
            f"{m.get('created_at')} [{m.get('event_level')}] {m.get('message')}"
            for m in messages
        ),
    )


def _log_instance_console(instances: list[dict]) -> None:
    """Log the serial console of each VM that failed to produce a runner.

    Everything above is GARM's side of the story, which ends at the last callback the
    VM managed to send. The bootstrap runs with ``set -x`` and echoes the reason it
    gave up, so when a VM stops calling back the console is the only place the cause
    is recorded -- and it distinguishes the cases that look identical from outside:
    no route to the callback URL (curl exit 7), a certificate the VM does not trust
    (exit 60), and a bootstrap that ran but failed later.

    Best effort: the console is a diagnostic aid on a path that has already failed, so
    a missing client, an expired credential or an instance GARM has already reaped
    must not replace the real failure with an error from this function.
    """
    sentinel_values = _credential_sentinels()
    for instance in instances:
        provider_id = instance.get("provider_id")
        if not provider_id:
            continue
        cmd = [
            "openstack",
            "console",
            "log",
            "show",
            "--lines",
            "200",
            str(provider_id),
        ]
        try:
            out = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error("Could not read the console of %s: %s", provider_id, exc)
            continue
        # The bootstrap echoes its callback bearer token and the runner's JIT
        # configuration under `set -x`, so this has to go through the redactor.
        logger.error(
            "=== Console log of %s (%s) ===\n%s%s",
            instance.get("name"),
            provider_id,
            _redact_sentinels(out.stdout, sentinel_values),
            _redact_sentinels(out.stderr, sentinel_values),
        )


def _wait_for_shell_capability(
    juju: jubilant.Juju,
    garm_app: str,
    instance_name: str,
    timeout: int = 10 * 60,
    poll_interval: int = 10,
) -> None:
    """Block until the runner's GARM agent reports that it can serve a shell.

    A runner reaches a registered state as soon as GitHub has seen it, which is
    before its agent has finished dialling the websocket back, so the capability
    has to be waited for separately rather than assumed from runner_status.

    Args:
        juju: Juju client for the model GARM is deployed in.
        garm_app: Name of the deployed GARM application.
        instance_name: Name of the GARM instance to poll.
        timeout: Seconds to wait before failing the test.
        poll_interval: Seconds between polls.
    """
    address = _get_garm_address(juju, garm_app)
    url = f"http://{address}:{GARM_API_PORT}/api/v1/instances/{instance_name}"
    token = _garm_login(juju, address)
    deadline = time.time() + timeout
    logger.info("Waiting for the agent on %s to advertise shell support", instance_name)

    while time.time() < deadline:
        try:
            response = requests.get(
                url, headers={"Authorization": f"Bearer {token}"}, timeout=30
            )
            if response.status_code == 401:
                # The poll window can outlive the JWT; renew and retry next pass.
                token = _garm_login(juju, address)
            else:
                response.raise_for_status()
                instance = response.json() or {}
                if (instance.get("capabilities") or {}).get("has_shell"):
                    return
                logger.info(
                    "Agent on %s not ready yet: capabilities=%s heartbeat=%s",
                    instance_name,
                    instance.get("capabilities"),
                    instance.get("heartbeat"),
                )
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Transient error polling GARM, retrying: %s", exc)
        time.sleep(poll_interval)

    _collect_debug_info(juju, garm_app)
    pytest.fail(
        f"The GARM agent on {instance_name} never advertised shell support within "
        f"{timeout}s, so no shell session could be opened."
    )


def _run_in_agent_shell(
    garm_cli: GarmCli, runner_name: str, command: str, timeout: int = 180
) -> str:
    """Run one command in a `garm-cli runner shell` session and return the transcript.

    Args:
        garm_cli: The client and the environment selecting its admin profile.
        runner_name: Name of the GARM instance to open a session on.
        command: Command to type at the remote prompt.
        timeout: Seconds to spend driving the session before giving up.

    Returns:
        Everything the session printed, with terminal control codes removed.
    """
    # garm-cli puts its stdin in raw mode and reads the window size from it, so
    # it has to be given a real terminal: over a pipe it fails before the
    # session is opened.
    master, slave = pty.openpty()
    process = subprocess.Popen(
        [str(garm_cli.binary), "runner", "shell", runner_name],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=garm_cli.env,
    )
    # Held only by the child from here on, so closing the master below is what
    # ends the session.
    os.close(slave)
    try:
        transcript = _drive_agent_shell(master, command, deadline=time.time() + timeout)
    finally:
        os.close(master)
        _terminate(process)

    logger.info("Agent shell transcript for %s: %s", runner_name, transcript)
    return transcript


def _drive_agent_shell(master: int, command: str, deadline: float) -> str:
    """Type a command and then an exit at the remote prompt, collecting the output.

    Args:
        master: File descriptor of the terminal the session runs on.
        command: Command to type at the remote prompt.
        deadline: Monotonic-ish wall clock time to stop reading at.

    Returns:
        Everything read from the session, with terminal control codes removed.
    """
    chunks: list[bytes] = []
    for line in (command, "exit"):
        # garm-cli discards anything typed before the session's ShellReady
        # arrives, so each line waits for the far side to settle first.
        _read_until_quiet(master, chunks, deadline)
        os.write(master, f"{line}\n".encode())
    _read_until_quiet(master, chunks, deadline)
    return ANSI_PATTERN.sub("", b"".join(chunks).decode(errors="replace"))


def _read_until_quiet(master: int, chunks: list[bytes], deadline: float) -> None:
    """Read from the session until it falls silent, or the deadline passes.

    The silence timer only starts once something has arrived, so the websocket
    handshake to GARM and on to the agent is never mistaken for a prompt that is
    ready to be typed at.

    Args:
        master: File descriptor of the terminal the session runs on.
        chunks: Accumulator the bytes read are appended to.
        deadline: Wall clock time to stop reading at.
    """
    seen = False
    last_read = time.time()
    while time.time() < deadline:
        readable, _, _ = select.select([master], [], [], 0.5)
        if not readable:
            if seen and time.time() - last_read >= SHELL_QUIET_PERIOD:
                return
            continue
        try:
            data = os.read(master, 65536)
        except OSError:
            # The terminal reports EIO once garm-cli has exited and closed its end.
            return
        if not data:
            return
        chunks.append(data)
        seen, last_read = True, time.time()


def _terminate(process: subprocess.Popen, grace: int = 10) -> None:
    """Reap garm-cli, killing it if closing its terminal was not enough.

    Args:
        process: The garm-cli process to reap.
        grace: Seconds to allow for each of the clean exit and the kill.
    """
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        logger.warning("garm-cli did not exit with its terminal closed; killing it")
        process.kill()
        process.wait(timeout=grace)
