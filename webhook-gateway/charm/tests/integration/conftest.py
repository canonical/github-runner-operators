# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import contextlib
import logging
from typing import Generator, cast, Iterator

import pytest
import jubilant

from tests.conftest import CHARM_FILE_PARAM, APP_IMAGE_PARAM

logger = logging.getLogger(__name__)

@pytest.fixture(name="use_existing_app", scope="module")
def use_existing_app_fixture(pytestconfig: pytest.Config) -> bool:
    """Return whether to use an existing app instead of deploying a new one."""
    return pytestconfig.getoption("--use-existing-app")


@pytest.fixture(name="charm_file", scope="module")
def charm_file_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the built charm file."""
    charm = pytestconfig.getoption(CHARM_FILE_PARAM)
    return charm


@pytest.fixture(name="app_image", scope="module")
def app_image_fixture(pytestconfig: pytest.Config) -> str | None:
    """Return the path to the flask app image"""
    app_image = pytestconfig.getoption(APP_IMAGE_PARAM)
    return app_image


@pytest.fixture(scope='module')
def juju():
    with jubilant.temp_model(keep=True) as juju:
        yield juju

@pytest.fixture(scope="module", name="app")
def deploy_app_fixture(juju: jubilant.Juju, charm_file: str, app_image: str) -> str:
    app_name = "webhook-gateway-k8s"


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
    "Return the controller name for lxd."
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
        # Always get back to the original controller and model
        juju.cli(
            "switch", f"{original_controller_name}:{original_model_name}", include_model=False
        )
    yield lxd_controller_name


@pytest.fixture(scope="module", name="lxd_model_name")
def lxd_model_name_fixture(juju: jubilant.Juju) -> str:
    "Return the model name for lxd."
    status = juju.status() #TODO fix this , too implicit
    return status.model.name


@pytest.fixture(scope="module", name="lxd_model")
def lxd_model_fixture(
    request: pytest.FixtureRequest, juju: jubilant.Juju, lxd_controller, lxd_model_name
) -> Iterator[str]:
    "Create the lxd_model and return its name."
    with jubilant_temp_controller(juju, lxd_controller):
        try:
            juju.add_model(lxd_model_name)
        except jubilant.CLIError as ex:
            if "already exists" not in ex.stderr:
                raise
    yield lxd_model_name
    keep_models = cast(bool, request.config.getoption("--keep-models"))
    if not keep_models:
        with jubilant_temp_controller(juju, lxd_controller):
            juju.destroy_model(lxd_model_name, destroy_storage=True, force=True)

@pytest.fixture(scope="module", name="rabbitmq_server_app")
def deploy_rabbitmq_server_fixture(juju: jubilant.Juju, lxd_controller, lxd_model) -> str:
    """Deploy rabbitmq server machine charm."""
    rabbitmq_server_name = "rabbitmq-server"

    with jubilant_temp_controller(juju, lxd_controller, lxd_model):
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
    # The return is a string with the name of the applications, but will not
    # contain the controller or model. Other apps can integrate to rabbitmq using this
    # name as there is a local offer with this name.
    return rabbitmq_server_name

@contextlib.contextmanager
def jubilant_temp_controller(
    juju: jubilant.Juju, controller: str, model: str = ""
) -> Generator[jubilant.Juju, None, None]:
    try:
        status = juju.status()
        original_controller_name = status.model.controller
        original_model_name = status.model.name
        juju.cli("switch", f"{controller}:{model}", include_model=False)
        yield juju
    finally:
        juju.cli(
            "switch", f"{original_controller_name}:{original_model_name}", include_model=False
        )