# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for webhook redelivery daemon startup."""

import jubilant
import pytest
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from tests.integration.helpers import (
    GITHUB_APP_ID_ENV_VAR,
    GITHUB_APP_INSTALLATION_ID_ENV_VAR,
    GITHUB_APP_PRIVATE_KEY_ENV_VAR,
    required_env,
    required_int_env,
    trigger_failed_workflow_job_delivery,
)

from conftest import GITHUB_PATH

DISPATCH_WORKFLOW_PATH = "copilot-collections-update.yml"


@retry(
    retry=retry_if_exception_type(AssertionError),
    stop=stop_after_attempt(5),
    wait=wait_fixed(20),
    reraise=True,
)
def assert_redelivery_logged(juju: jubilant.Juju, unit_name: str) -> None:
    """Assert successful webhook redelivery appears in webhook gateway logs."""
    result = juju.exec(
        "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble logs -n all",
        unit=unit_name,
    )
    assert "redelivered failed webhooks" in result.stdout

@pytest.mark.usefixtures("webhook_gateway_with_rabbitmq")
def test_webhook_gateway_redelivery_daemon_start(
    juju: jubilant.Juju,
    webhook_gateway_app: str,
    github_test_hook,
):
    """
    arrange: A test GitHub webhook is created for the configured repository.
    act: Configure redelivery daemon settings with GitHub App credentials.
    assert: The charm remains active, the redelivery daemon starts,
        and a redelivery cycle succeeds.
    """
    github_app_private_key_secret_uri = juju.add_secret(
        name="github-app-private-key",
        content={"value": required_env(GITHUB_APP_PRIVATE_KEY_ENV_VAR)},
    )
    juju.grant_secret(github_app_private_key_secret_uri, webhook_gateway_app)

    juju.config(
        webhook_gateway_app,
        values={
            "github-path": GITHUB_PATH,
            "webhook-id": github_test_hook.id,
            "redelivery-interval": 30,
            "github-app-id": required_int_env(GITHUB_APP_ID_ENV_VAR),
            "github-app-installation-id": required_int_env(
                GITHUB_APP_INSTALLATION_ID_ENV_VAR
            ),
            "github-app-private-key": github_app_private_key_secret_uri,
        },
    )

    juju.wait(
        lambda status: jubilant.all_active(status, webhook_gateway_app),
        error=lambda status: jubilant.any_error(status, webhook_gateway_app),
        timeout=5 * 60,
        delay=10,
    )

    unit_name = f"{webhook_gateway_app}/0"
    result = juju.exec(
        "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble logs -n all",
        unit=unit_name,
    )
    assert "redelivery daemon started" in result.stdout
    assert str(github_test_hook.id) in result.stdout

    trigger_failed_workflow_job_delivery(GITHUB_PATH, DISPATCH_WORKFLOW_PATH)
    assert_redelivery_logged(juju, unit_name)
