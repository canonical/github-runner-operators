# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
import base64
import json
import os
import time
from typing import Any

import jubilant
import pytest
from github import Github
from github.Auth import AppAuth, AppInstallationAuth

GITHUB_APP_ID_ENV_VAR = "TEST_GITHUB_APP_ID"
GITHUB_APP_INSTALLATION_ID_ENV_VAR = "TEST_GITHUB_APP_INSTALLATION_ID"
GITHUB_APP_PRIVATE_KEY_ENV_VAR = "TEST_GITHUB_APP_PRIVATE_KEY"
GITHUB_PATH_ENV_VAR = "TEST_GITHUB_PATH"


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
