# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import contextlib
import logging
import secrets
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


@pytest.fixture(name="model_name", scope="module")
def model_name_fixture(pytestconfig: pytest.Config) -> str:
    return "jubilant-" + secrets.token_hex(4)


@pytest.fixture(scope="module")
def juju(keep_models: bool, model_name: str) -> Iterator[jubilant.Juju]:
    with jubilant_temp_model(keep=keep_models, model=model_name) as juju:
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


@pytest.fixture(scope="module", name="lxd_controller_name")
def lxd_controller_name_fixture() -> str:
    """Return the controller name for lxd."""
    return "localhost"


@pytest.fixture(scope="module", name="lxd_controller")
def lxd_controller(
    juju: jubilant.Juju,
    lxd_controller_name,
) -> str:
    status = juju.status()
    original_controller_name = status.model.controller
    original_model_name = status.model.name
    lxd_cloud_name = "lxd"
    try:
        juju.cli("bootstrap", lxd_cloud_name, lxd_controller_name, include_model=False)
    except jubilant.CLIError as ex:
        if "already exists" not in ex.stderr:
            raise
    finally:
        juju.cli(
            "switch", f"{original_controller_name}:{original_model_name}", include_model=False
        )
    return lxd_controller_name


@pytest.fixture(scope="module", name="lxd_model")
def lxd_model_fixture(
    request: pytest.FixtureRequest, juju: jubilant.Juju, lxd_controller: str, keep_models: bool
) -> Iterator[str]:
    """Create the lxd_model and return its name."""
    current_model_name = juju.model
    with jubilant_switch_controller(juju, lxd_controller):
        try:
            juju.add_model(current_model_name)
        except jubilant.CLIError as ex:
            if "already exists" not in ex.stderr:
                raise
    yield current_model_name
    if not keep_models:
        with jubilant_switch_controller(juju, lxd_controller):
            juju.destroy_model(current_model_name, destroy_storage=True, force=True)


@pytest.fixture(scope="module", name="rabbitmq_server_app")
def deploy_rabbitmq_server_fixture(juju: jubilant.Juju, lxd_controller, lxd_model) -> str:
    """Deploy rabbitmq server machine charm."""
    rabbitmq_server_name = "rabbitmq-server"

    with jubilant_switch_controller(juju, lxd_controller, lxd_model):
        if juju.status().apps.get(rabbitmq_server_name):
            logger.info("rabbitmq server already deployed")
            return rabbitmq_server_name

        juju.deploy(
            rabbitmq_server_name,
            channel="edge",
        )

        juju.cli("offer", f"{rabbitmq_server_name}:amqp", include_model=False)
        juju.wait(
            lambda status: jubilant.all_active(status, rabbitmq_server_name),
            timeout=6 * 60,
            delay=10,
        )
    # Add the offer in the original model
    offer_name = f"{lxd_controller}:admin/{lxd_model}.{rabbitmq_server_name}"
    juju.cli("consume", offer_name, include_model=False)
    return rabbitmq_server_name


@contextlib.contextmanager
def jubilant_switch_controller(
    juju: jubilant.Juju, controller: str, model: str = ""
) -> Iterator[jubilant.Juju]:
    original_controller_name = original_model_name = None
    try:
        status = juju.status()
        original_controller_name = status.model.controller
        original_model_name = status.model.name
        juju.cli("switch", f"{controller}:{model}", include_model=False)
        yield juju
    finally:
        if original_controller_name and original_model_name:
            juju.cli(
                "switch", f"{original_controller_name}:{original_model_name}", include_model=False
            )


@contextlib.contextmanager
def jubilant_temp_model(model: str, keep: bool = False) -> Iterator[jubilant.Juju]:
    juju = jubilant.Juju()
    juju.add_model(model)
    try:
        yield juju
    finally:
        if not keep:
            juju.destroy_model(model, destroy_storage=True, force=True)
