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
    """Deploy the garm-configurator application with mock config.

    Returns the application name once the app reaches Active.
    """
    app_name = "garm-configurator"
    juju.deploy(charm=garm_configurator_charm_file, app=app_name)
    juju.wait(
        lambda status: jubilant.all_blocked(status, app_name),
        timeout=5 * 60,
        delay=10,
    )

    password_secret_uri = juju.add_secret(
        name="openstack-password", content={"value": "fake-password"}
    )
    private_key_secret_uri = juju.add_secret(
        name="github-app-private-key", content={"value": "fake-private-key"}
    )
    juju.grant_secret(password_secret_uri, app_name)
    juju.grant_secret(private_key_secret_uri, app_name)

    juju.config(
        app_name,
        values={
            "openstack-auth-url": "https://keystone.example.com:5000/v3",
            "openstack-username": "admin",
            "openstack-password": password_secret_uri,
            "openstack-project-name": "myproject",
            "openstack-user-domain-name": "Default",
            "openstack-project-domain-name": "Default",
            "openstack-region-name": "RegionOne",
            "openstack-network": "external-net",
            "github-app-client-id": "12345",
            "github-app-installation-id": "67890",
            "github-app-private-key": private_key_secret_uri,
        },
    )
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
    arrange: garm-configurator charm deployed with valid mock configuration.
    act: Check the application status.
    assert: Application is in Active state.
    """
    status = juju.status()
    assert jubilant.all_active(status, garm_configurator_app)
