# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
from typing import Iterator

import jubilant
import pytest

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
    with jubilant.temp_model(keep=keep_models) as juju:
        yield juju


@pytest.fixture(scope="module", name="planner_app")
def deploy_planner_app_fixture(
    juju: jubilant.Juju, planner_charm_file: str, planner_app_image: str
) -> str:
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
    juju.config(app_name, values={"metrics-port": 9464})
    return app_name


@pytest.fixture(scope="module", name="webhook_gateway_app")
def deploy_webhook_gateway_app_fixture(
    juju: jubilant.Juju, webhook_gateway_charm_file: str, webhook_gateway_app_image: str
) -> str:
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


@pytest.fixture(scope="module", name="planner_with_rabbitmq")
def integrate_planner_rabbitmq_fixture(
    juju: jubilant.Juju, planner_app: str, rabbitmq: str
) -> None:
    """Integrate planner with rabbitmq."""
    juju.integrate(planner_app, rabbitmq)
    juju.wait(
        lambda status: jubilant.all_active(status, planner_app),
        timeout=(10 * 60),
        delay=30,
    )


@pytest.fixture(scope="module", name="webhook_gateway_with_rabbitmq")
def integrate_webhook_gateway_rabbitmq_fixture(
    juju: jubilant.Juju, webhook_gateway_app: str, rabbitmq: str
) -> None:
    """Integrate webhook gateway with rabbitmq."""
    juju.integrate(webhook_gateway_app, rabbitmq)
    juju.wait(
        lambda status: jubilant.all_active(status, webhook_gateway_app),
        timeout=(10 * 60),
        delay=30,
    )


@pytest.fixture(scope="module", name="both_apps_with_rabbitmq")
def integrate_both_rabbitmq_fixture(
    juju: jubilant.Juju,
    planner_with_rabbitmq: None,
    webhook_gateway_with_rabbitmq: None,
) -> None:
    """Integrate both planner and webhook gateway with rabbitmq."""
    # Dependencies handle the integrations
    pass


@pytest.fixture(scope="module", name="postgresql")
def deploy_postgresql_server_fixture(
    juju: jubilant.Juju, planner_with_rabbitmq: None
) -> str:
    """Deploy postgresql charm and integrate it with the planner app.

    Planner requires both rabbitmq and postgresql, so this fixture depends on
    planner_with_rabbitmq being set up first.
    """
    postgresql_app = "postgresql-k8s"
    planner_app = "github-runner-planner"

    juju.deploy(postgresql_app, channel="16/edge", trust=True)

    juju.integrate(planner_app, postgresql_app)
    juju.wait(
        lambda status: jubilant.all_active(status, planner_app),
        timeout=(10 * 60),
        delay=30,
    )
    return postgresql_app


@pytest.fixture(scope="module", name="planner_and_webhook_gateway_ready")
def planner_and_webhook_gateway_ready_fixture(
    postgresql: str,
    webhook_gateway_with_rabbitmq: None,
) -> None:
    """Fixture that ensures both planner and webhook gateway are fully integrated and ready.

    Depends on:
    - postgresql: which ensures planner has both PostgreSQL and RabbitMQ integrated
    - webhook_gateway_with_rabbitmq: which ensures webhook gateway has RabbitMQ integrated
    """
    pass
