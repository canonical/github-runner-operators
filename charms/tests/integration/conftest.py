# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import secrets
import string
import textwrap
from typing import Iterator

import jubilant
import pytest
import requests
from tests.conftest import (
    CHARM_FILE_PARAM,
    PLANNER_IMAGE_PARAM,
    WEBHOOK_GATEWAY_IMAGE_PARAM,
)

logger = logging.getLogger(__name__)


@pytest.fixture(name="planner_charm_file", scope="module")
def planner_charm_file_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the built planner charm file."""
    charm = pytestconfig.getoption(CHARM_FILE_PARAM)
    if len(charm) > 1:
        planner_charm = [file for file in charm if "planner" in file]
        return planner_charm[0]
    return charm


@pytest.fixture(name="planner_app_image", scope="module")
def planner_app_image_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the planner app image."""
    app_image = pytestconfig.getoption(PLANNER_IMAGE_PARAM)
    return app_image


@pytest.fixture(name="webhook_gateway_charm_file", scope="module")
def webhook_gateway_charm_file_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the built webhook gateway charm file."""
    charm = pytestconfig.getoption(CHARM_FILE_PARAM)
    if len(charm) > 1:
        webhook_gateway_charm = [file for file in charm if "webhook-gateway" in file]
        return webhook_gateway_charm[0]
    return charm


@pytest.fixture(name="webhook_gateway_app_image", scope="module")
def webhook_gateway_app_image_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the webhook gateway app image."""
    app_image = pytestconfig.getoption(WEBHOOK_GATEWAY_IMAGE_PARAM)
    return app_image


@pytest.fixture(name="keep_models", scope="module")
def keep_models_fixture(pytestconfig: pytest.Config) -> bool:
    """Return whether to keep models after deploying."""
    return pytestconfig.getoption("--keep-models")


@pytest.fixture(scope="module")
def juju(keep_models: bool) -> Iterator[jubilant.Juju]:
    """Provide a temporary Juju model for the duration of the module.

    Creates a temporary model (optionally kept based on --keep-models) and yields a
    `jubilant.Juju` handle for deployments, relations, and config operations.
    The model is cleaned up automatically at the end of the module unless kept.
    """
    with jubilant.temp_model(keep=keep_models) as juju:
        yield juju


def _generate_admin_token() -> str:
    alphabet = string.ascii_letters + string.digits + "_-"
    suffix = "".join(secrets.choice(alphabet) for _ in range(20))
    return f"planner_v0_{suffix}"


@pytest.fixture(scope="module", name="planner_admin_token_value")
def planner_admin_token_value_fixture() -> str:
    """Generate and return the planner admin token value for this test module."""
    return _generate_admin_token()


@pytest.fixture(scope="module", name="planner_admin_token_uri")
def create_planner_admin_token_uri_fixture(
    juju: jubilant.Juju, planner_admin_token_value: str
) -> str:
    """Create a Juju secret for the planner admin token and return its URI.

    Secret is created before the app is deployed so it can be referenced in config.
    Granting to the app is done after deploy in the planner_app fixture.
    """
    secret_uri = juju.add_secret(
        name="planner-admin-token", content={"value": planner_admin_token_value}
    )
    return secret_uri


@pytest.fixture(scope="module", name="planner_app")
def deploy_planner_app_fixture(
    juju: jubilant.Juju,
    planner_charm_file: str,
    planner_app_image: str,
    planner_admin_token_uri: str,
) -> str:
    """Deploy the planner application with its OCI image and admin token secret.

    - Deploys the planner charm with the provided image resource.
    - Waits for the application to block pending configuration.
    - Grants the pre-created admin token secret to the application.
    - Sets required configuration including the secret reference and metrics port.

    Returns the application name once initial configuration is applied.
    """
    app_name = "github-runner-planner"

    resources = {
        "app-image": planner_app_image,
    }
    juju.deploy(charm=planner_charm_file, app=app_name, resources=resources)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )
    juju.grant_secret(planner_admin_token_uri, app_name)
    juju.config(
        app_name, values={"metrics-port": 9464, "admin-token": planner_admin_token_uri}
    )
    return app_name


@pytest.fixture(scope="module", name="user_token")
def user_token_fixture(
    juju: jubilant.Juju,
    planner_app: str,
    planner_admin_token_value: str,
) -> str:
    """Create a regular user token from the planner app using the admin token and return it."""
    status = juju.status()
    unit = f"{planner_app}/0"
    planner_ip = status.apps[planner_app].units[unit].address
    url = f"http://{planner_ip}:8080/api/v1/auth/token/github-runner"
    headers = {"Authorization": f"Bearer {planner_admin_token_value}"}
    resp = requests.post(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    token = data.get("token", "")
    assert token, "expected non-empty user token from planner"
    return token


@pytest.fixture(scope="module", name="webhook_gateway_app")
def deploy_webhook_gateway_app_fixture(
    juju: jubilant.Juju, webhook_gateway_charm_file: str, webhook_gateway_app_image: str
) -> str:
    """Deploy the webhook gateway application with its OCI image and secret.

    - Deploys the webhook gateway charm with the provided image resource.
    - Waits for the application to block pending configuration.
    - Creates and grants a placeholder webhook secret to the application.
    - Configures the application with the secret and metrics port.

    Returns the application name once initial configuration is applied.
    """
    app_name = "github-runner-webhook-gateway"

    resources = {
        "app-image": webhook_gateway_app_image,
    }
    juju.deploy(charm=webhook_gateway_charm_file, app=app_name, resources=resources)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )
    secret_uri = juju.add_secret(name="webhook", content={"value": "fake-secret"})
    juju.grant_secret(secret_uri, app_name)
    juju.config(app_name, values={"webhook-secret": secret_uri, "metrics-port": 9464})
    return app_name


@pytest.fixture(scope="module", name="rabbitmq")
def deploy_rabbitmq_server_fixture(juju: jubilant.Juju) -> str:
    """Deploy rabbitmq charm (without integrations)."""
    rabbitmq_app = "rabbitmq-k8s"
    juju.deploy(rabbitmq_app, channel="3.12/edge", trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status, rabbitmq_app),
        timeout=(10 * 60),
        delay=30,
    )
    return rabbitmq_app


@pytest.fixture(scope="module", name="webhook_gateway_with_rabbitmq")
def integrate_webhook_gateway_rabbitmq_fixture(
    juju: jubilant.Juju, webhook_gateway_app: str, rabbitmq: str
) -> str:
    """Integrate webhook gateway with rabbitmq.

    Returns the webhook gateway app name after ensuring integration is active.
    """
    juju.integrate(webhook_gateway_app, rabbitmq)
    juju.wait(
        lambda status: jubilant.all_active(status, webhook_gateway_app),
        timeout=(10 * 60),
        delay=30,
    )
    return webhook_gateway_app


@pytest.fixture(scope="module", name="postgresql")
def deploy_postgresql_server_fixture(juju: jubilant.Juju) -> str:
    """Deploy postgresql charm (without integrations)."""
    postgresql_app = "postgresql-k8s"
    juju.deploy(postgresql_app, channel="16/edge", trust=True)
    juju.wait(
        lambda status: jubilant.all_active(status, postgresql_app),
        timeout=(10 * 60),
        delay=30,
    )
    return postgresql_app


@pytest.fixture(scope="module", name="planner_with_integrations")
def integrate_planner_rabbitmq_postgresql_fixture(
    juju: jubilant.Juju, planner_app: str, rabbitmq: str, postgresql: str
) -> str:
    """Integrate planner with rabbitmq and postgresql.

    Returns the planner app name after ensuring all integrations are active.
    """
    juju.integrate(planner_app, rabbitmq)
    juju.integrate(planner_app, postgresql)

    juju.wait(
        lambda status: jubilant.all_active(status, planner_app),
        timeout=(10 * 60),
        delay=30,
    )
    return planner_app


@pytest.fixture(scope="module", name="any_charm_github_runner_app")
def deploy_any_charm_github_runner_app_fixture( juju: jubilant.Juju) -> str:
    """Deploy any charm to act as a GitHub runner application."""
    app_name = "github-runner"

    any_charm_src_overwrite = {
        "any_charm.py": textwrap.dedent(
            f"""\
            from any_charm_base import AnyCharmBase

            class AnyCharm(AnyCharmBase):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.framework.observe(self.on['github-runner-planner-v0'].\
relation_changed, self._image_relation_changed)

                def _image_relation_changed(self, event):
                    pass
            """
        ),
    }
    juju.deploy(
        "any-charm",
        app=app_name,
        channel="latest/beta",
        config={"src-overwrite": any_charm_src_overwrite},
    )
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=6 * 60,
        delay=10,
    )
    return app_name
