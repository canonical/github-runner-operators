# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import base64
import datetime
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import jubilant
import pytest
from github import Github, GithubException
from github.Auth import AppAuth, AppInstallationAuth

GITHUB_APP_ID_ENV_VAR = "TEST_GITHUB_APP_ID"
GITHUB_APP_INSTALLATION_ID_ENV_VAR = "TEST_GITHUB_APP_INSTALLATION_ID"
GITHUB_APP_PRIVATE_KEY_ENV_VAR = "TEST_GITHUB_APP_PRIVATE_KEY"
GITHUB_PATH_ENV_VAR = "TEST_GITHUB_PATH"

E2E_GITHUB_APP_ID_ENV_VAR = "E2E_GITHUB_APP_ID"
E2E_GITHUB_APP_INSTALLATION_ID_ENV_VAR = "E2E_GITHUB_APP_INSTALLATION_ID"
E2E_GITHUB_APP_PRIVATE_KEY_ENV_VAR = "E2E_GITHUB_APP_PRIVATE_KEY"

# Set by GitHub Actions to "owner/repo"; the GARM E2E targets the repository it runs
# from, so the scaleset entity, the dispatch target and the workflow file agree by
# construction and no separate path setting can drift out of sync with them.
GITHUB_REPOSITORY_ENV_VAR = "GITHUB_REPOSITORY"


@dataclass(frozen=True)
class GithubAppEnv:
    """Names of the environment variables holding one GitHub App's credentials.

    The integration suite and the GARM E2E authenticate as different Apps, installed on
    different repositories with different permissions, so each needs its own set.
    """

    app_id: str
    installation_id: str
    private_key: str


INTEGRATION_APP_ENV = GithubAppEnv(
    app_id=GITHUB_APP_ID_ENV_VAR,
    installation_id=GITHUB_APP_INSTALLATION_ID_ENV_VAR,
    private_key=GITHUB_APP_PRIVATE_KEY_ENV_VAR,
)
E2E_APP_ENV = GithubAppEnv(
    app_id=E2E_GITHUB_APP_ID_ENV_VAR,
    installation_id=E2E_GITHUB_APP_INSTALLATION_ID_ENV_VAR,
    private_key=E2E_GITHUB_APP_PRIVATE_KEY_ENV_VAR,
)

# A throwaway RSA key used only to satisfy GARM's GitHub App credential parsing in
# integration tests. Not a real secret.
TEST_RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICXwIBAAKBgQC2tCW5B18y5VnqqokOeamJgasI3H1405WWv7FmWl31I1Cgabhi
MFcHdNECXFUC3wtqo/bXyCQbANRBkpZudJfSGos3+1iOJK1fd+MU8ntHVtgpvb5j
whdFSVJ9EL4/2u0K0S+fIyilD9q7K5mhk0MYLYWumPIRLkbtwr9a7LgY5wIDAQAB
AoGBAKIQGCoRjPNjmCfdT6fEaYtstt8sXiwQWu+WaHDnFdL9mWZBgOmwAXK+vyt9
5XafjMvyV2I+yTAewyjLM58U0xlslJu6Bk0Zw920sTmK9Qvvq/2mjsqw+PWr9rRx
qZFDCefAlB0Npo9tXHAf3ec5+vlm4QsEl6dty+Wx6aSHHMRpAkEA8e5IwkJZFcWO
aCc8Z+cnoidomlkvGlruncXMG1KhisQTleQVc1bM8tIZq2nNUG1zKJqHeCacQLiV
LKALnZDSCwJBAMFUIHd7ikYaAgTvrAKmzOZlMKVuGr2SHPODWoaWkEagEsrOw+H2
PYonSYkbzPyXH6iKUOhWH+ZA1r6K1lhdWhUCQQCquaTOsVN8cbVU+ps+F3l4jKbc
hSMgThsla3flsCIfcs7/b71Tb2Wh1XIX7Mnef95MQQBoYZbSdW+P1kFcJ96RAkEA
oSyuqI4BGDJkjpL1l3xSBJ5F8RUbDAI9SrKujNgHTinzoMrCOabdZUkdoEXiHo8r
IIq3qwrqKz7RCSecTSz+hQJBAJDKODanbnrPxNDgmIp52BMtiYI4vv7gKp/MSW0N
PG8an+PHNVGDEj1cOOwp/YNQieRp/WPH6bpBtwwe0r6pQZQ=
-----END RSA PRIVATE KEY-----"""


def poll_grafana_dashboard_templates(
    juju: jubilant.Juju, consumer_unit: str, attempts: int = 24, interval: int = 5
) -> dict[str, Any]:
    """Poll for dashboard templates via the grafana-dashboard consumer's relation data.

    Checks show-unit on the consumer side, where application-data contains
    the provider's data (including the dashboards key).
    Returns the templates dict if found, or an empty dict after all attempts are exhausted.
    """
    for _ in range(attempts):
        stdout = juju.cli("show-unit", consumer_unit, "--format=json")
        result = json.loads(stdout)
        for relation in result[consumer_unit]["relation-info"]:
            if relation["endpoint"] == "require-grafana-dashboard":
                dashboards_raw = relation["application-data"].get("dashboards")
                if dashboards_raw:
                    dashboards = json.loads(dashboards_raw)
                    templates = dashboards.get("templates", {})
                    if templates:
                        return templates
        time.sleep(interval)
    return {}


def required_env(name: str) -> str:
    """Return a required environment variable or fail the running test."""
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is required but was empty or unset")
    return value


def required_int_env(name: str) -> int:
    """Return a required integer environment variable or fail with context."""
    value = required_env(name)
    try:
        return int(value)
    except ValueError:
        pytest.fail(f"{name} must be an integer")


def github_app_private_key(env: GithubAppEnv = INTEGRATION_APP_ENV) -> str:
    """Return the GitHub App private key as a PEM string.

    Accepts either the PEM as GitHub issues it or its base64 encoding, so the same
    secret works wherever it is set from.
    """
    # CI carries the key base64-encoded because the channels it crosses take one
    # KEY=value per line, but a developer exporting it locally has no such constraint
    # and should not have to discover the encoding.
    value = required_env(env.private_key)
    if "-----BEGIN" in value:
        return value
    try:
        # validate=True: the default discards characters outside the alphabet, which
        # would turn a mangled key into plausible-looking bytes instead of an error.
        return base64.b64decode(value, validate=True).decode()
    except ValueError:
        pytest.fail(
            f"{env.private_key} is neither a PEM nor valid base64. Set it to the key "
            f"file's contents."
        )


def create_github_app_client(env: GithubAppEnv = INTEGRATION_APP_ENV) -> Github:
    """Create a GitHub client authenticated as the given App's installation."""
    private_key = github_app_private_key(env)
    app_auth = AppAuth(
        app_id=required_int_env(env.app_id),
        private_key=private_key,
    )
    installation_auth = AppInstallationAuth(
        app_auth=app_auth,
        installation_id=required_int_env(env.installation_id),
    )
    return Github(auth=installation_auth)


def trigger_failed_workflow_job_delivery(
    repo_path: str,
    workflow_path: str,
) -> None:
    """Dispatch a workflow run to emit a workflow_job event for webhook redelivery tests."""
    github_client = create_github_app_client()
    repo = github_client.get_repo(repo_path)
    workflow = repo.get_workflow(workflow_path)
    # throw=True: the default returns False on error, so a dispatch the App is not
    # permitted to make would leave the test asserting against the webhook ping
    # delivery alone and still passing.
    workflow.create_dispatch(ref=repo.default_branch, throw=True)


def dispatch_workflow(
    github_client: Github,
    repo_path: str,
    workflow_path: str,
    ref: str,
    inputs: dict[str, Any],
) -> int:
    """Dispatch a workflow run and return its run ID.

    Args:
        github_client: Authenticated PyGithub instance.
        repo_path: ``org/repo`` string.
        workflow_path: Path in the repository to the workflow file.
        ref: Git branch to run the workflow on. The run is found again through
            a branch-scoped listing, so a tag ref would dispatch but never resolve.
        inputs: Workflow dispatch inputs.

    Returns:
        The workflow run ID.
    """
    repo = github_client.get_repo(repo_path)
    workflow = repo.get_workflow(workflow_path)
    # Snapshot existing run IDs to disambiguate concurrent or recent runs
    existing_run_ids = {run.id for run in workflow.get_runs(branch=ref, event="workflow_dispatch")}
    try:
        # throw=True: the default returns False on error, which would surface a
        # permissions failure as an unrelated "no new run appeared" timeout below.
        workflow.create_dispatch(ref=ref, inputs=inputs, throw=True)
    except GithubException as e:
        pytest.fail(f"dispatch_workflow failed: {e.status} {e.data}")

    # After dispatch, poll for the run ID that is not in the initial snapshot.
    for _ in range(30):
        time.sleep(2)
        runs = workflow.get_runs(branch=ref, event="workflow_dispatch")
        for run in runs:
            if run.id not in existing_run_ids:
                return run.id

    pytest.fail(
        f"Workflow {workflow_path} did not produce a new run on {ref} after dispatch"
    )


def wait_for_completion(
    github_client: Github,
    repo_path: str,
    run_id: int,
    poll_interval: int = 15,
    timeout: int = 600,
) -> str | None:
    """Poll a workflow run until it completes, returning the conclusion.

    Args:
        github_client: Authenticated PyGithub instance.
        repo_path: ``org/repo`` string.
        run_id: Workflow run ID to monitor.
        poll_interval: Seconds between polls.
        timeout: Max seconds to wait.

    Returns:
        The run conclusion string (e.g. ``"success"``, ``"failure"``) or None.
    """
    repo = github_client.get_repo(repo_path)
    deadline = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=timeout
    )
    while datetime.datetime.now(datetime.timezone.utc) < deadline:
        run = repo.get_workflow_run(run_id)
        if run.status == "completed":
            return run.conclusion
        time.sleep(poll_interval)
    pytest.fail(f"Workflow run {run_id} did not complete within {timeout}s")
