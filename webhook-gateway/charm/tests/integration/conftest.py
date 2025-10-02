# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
from typing import Iterator

import jubilant
import pytest

from tests.conftest import APP_IMAGE_PARAM, CHARM_FILE_PARAM

logger = logging.getLogger(__name__)


@pytest.fixture(name="charm_file", scope="module")
def charm_file_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the built charm file."""
    charm = pytestconfig.getoption(CHARM_FILE_PARAM)
    return charm


@pytest.fixture(name="app_image", scope="module")
def app_image_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the app image."""
    app_image = pytestconfig.getoption(APP_IMAGE_PARAM)
    return app_image


@pytest.fixture(name="keep_models", scope="module")
def keep_models_fixture(pytestconfig: pytest.Config) -> bool:
    """Return whether to keep models after deploying."""
    return pytestconfig.getoption("--keep-models")


@pytest.fixture(scope="module")
def juju(keep_models: bool) -> Iterator[jubilant.Juju]:
    with jubilant.temp_model(keep=keep_models) as juju:
        yield juju


@pytest.fixture(scope="module", name="app")
def deploy_app_fixture(juju: jubilant.Juju, charm_file: str, app_image: str) -> str:
    app_name = "github-runner-webhook-gateway"

    resources = {
        "app-image": app_image,
    }
    juju.deploy(charm=charm_file, app=app_name, resources=resources)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=6 * 60,
        delay=10,
    )
    secret_uri = juju.add_secret(name="webhook", content={"value": "fake-secret"})
    juju.grant_secret(secret_uri, app_name)
    juju.config(app_name, values={"webhook-secret": secret_uri})
    return app_name


@pytest.fixture(scope="module", name="rabbitmq")
def deploy_rabbitmq_server_fixture(juju: jubilant.Juju, app: str) -> str:
    """Deploy rabbitmq charm and integrate it with the app."""
    rabbitmq_app = "rabbitmq-k8s"

    juju.deploy(
        rabbitmq_app,
        channel="3.12/edge",
    )

    juju.integrate(app, rabbitmq_app)
    juju.wait(
        lambda status: jubilant.all_active(status, app),
        timeout=(10 * 60),
        delay=30,
    )
    return rabbitmq_app
