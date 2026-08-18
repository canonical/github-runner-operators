# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import base64
import datetime
import json
import os
import time
from typing import Any

import jubilant
import pytest
from github import Github, GithubException
from github.Auth import AppAuth, AppInstallationAuth

GITHUB_APP_ID_ENV_VAR = "TEST_GITHUB_APP_ID"
GITHUB_APP_INSTALLATION_ID_ENV_VAR = "TEST_GITHUB_APP_INSTALLATION_ID"
GITHUB_APP_PRIVATE_KEY_ENV_VAR = "TEST_GITHUB_APP_PRIVATE_KEY"
GITHUB_PATH_ENV_VAR = "TEST_GITHUB_PATH"

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
        pytest.fail(f"{name} is required for webhook redelivery integration test")
    return value


def required_int_env(name: str) -> int:
    """Return a required integer environment variable or fail with context."""
    value = required_env(name)
    try:
        return int(value)
    except ValueError:
        pytest.fail(f"{name} must be an integer")


def create_github_app_client() -> Github:
    """Create a GitHub client authenticated as the test app installation."""
    # Private key is stored base64-encoded in CI secrets to avoid GITHUB_ENV multiline issues.
    private_key = base64.b64decode(required_env(GITHUB_APP_PRIVATE_KEY_ENV_VAR)).decode()
    app_auth = AppAuth(
        app_id=required_int_env(GITHUB_APP_ID_ENV_VAR),
        private_key=private_key,
    )
    installation_auth = AppInstallationAuth(
        app_auth=app_auth,
        installation_id=required_int_env(GITHUB_APP_INSTALLATION_ID_ENV_VAR),
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
    workflow.create_dispatch(ref=repo.default_branch)


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
        ref: Git ref (branch or tag) to run the workflow on.
        inputs: Workflow dispatch inputs.

    Returns:
        The workflow run ID.
    """
    repo = github_client.get_repo(repo_path)
    workflow = repo.get_workflow(workflow_path)
    start_time = datetime.datetime.now(datetime.timezone.utc)
    try:
        workflow.create_dispatch(ref=ref, inputs=inputs)
    except GithubException as e:
        pytest.fail(f"dispatch_workflow failed: {e.status} {e.data}")

    # After dispatch, poll for the run that was created after our dispatch call.
    for _ in range(30):
        time.sleep(2)
        runs = workflow.get_runs(branch=ref, event="workflow_dispatch")
        for run in runs:
            # created_at is UTC timezone-aware in PyGithub
            created_at = run.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
            if created_at >= start_time - datetime.timedelta(seconds=5):
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
) -> str:
    """Poll a workflow run until it completes, returning the conclusion.

    Args:
        github_client: Authenticated PyGithub instance.
        repo_path: ``org/repo`` string.
        run_id: Workflow run ID to monitor.
        poll_interval: Seconds between polls.
        timeout: Max seconds to wait.

    Returns:
        The run conclusion string (e.g. ``"success"``, ``"failure"``).
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
