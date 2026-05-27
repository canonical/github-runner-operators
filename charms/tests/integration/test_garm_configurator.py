# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the garm-configurator charm."""

import logging

import jubilant
import pytest

from tests.conftest import CHARM_FILE_PARAM

logger = logging.getLogger(__name__)


@pytest.fixture(name="garm_configurator_charm_file", scope="module")
def garm_configurator_charm_file_fixture(pytestconfig: pytest.Config) -> str:
    """Return the path to the built garm-configurator charm file."""
    charm = pytestconfig.getoption(CHARM_FILE_PARAM)
    if not charm:
        pytest.skip(
            f"missing required {CHARM_FILE_PARAM} option for garm-configurator integration tests"
        )
    if len(charm) > 1:
        configurator_charms = [f for f in charm if "garm-configurator" in f]
        if not configurator_charms:
            raise pytest.UsageError(
                f"no garm-configurator charm file found among {CHARM_FILE_PARAM} values: {charm}"
            )
        return configurator_charms[0]
    return charm[0]


@pytest.fixture(name="garm_configurator_app", scope="module")
def deploy_garm_configurator_app_fixture(
    juju: jubilant.Juju,
    garm_configurator_charm_file: str,
) -> str:
    """Deploy the garm-configurator application standalone with no relations.

    Returns the application name once the app reaches Active.
    """
    app_name = "garm-configurator"
    juju.deploy(charm=garm_configurator_charm_file, app=app_name)
    juju.wait(
        lambda status: jubilant.all_active(status, app_name),
        timeout=5 * 60,
        delay=10,
    )
    return app_name


def test_garm_configurator_deploys_active(
    juju: jubilant.Juju,
    garm_configurator_app: str,
) -> None:
    """
    arrange: garm-configurator charm deployed with no relations wired.
    act: Check the application status.
    assert: Application is in Active state.
    """
    status = juju.status()
    assert jubilant.all_active(status, garm_configurator_app)
