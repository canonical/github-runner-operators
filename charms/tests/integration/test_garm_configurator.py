# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the garm-configurator charm."""

import json

import jubilant
import pytest


@pytest.fixture(name="garm_configurator_app", scope="module")
def deploy_garm_configurator_app_fixture(
    juju: jubilant.Juju,
    garm_configurator_charm_file: str,
) -> str:
    """Deploy the garm-configurator application with mock config.

    Returns the application name once the app reaches Waiting (config valid,
    image builder relation not yet connected).
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
            "github-app-id": "12345",
            "github-app-installation-id": "67890",
            "github-app-private-key": private_key_secret_uri,
            "name": "test-scaleset",
            "flavor": "m1.large",
            "os-arch": "amd64",
            "repo": "myorg/myrepo",
        },
    )
    juju.wait(
        lambda status: jubilant.all_waiting(status, app_name),
        timeout=5 * 60,
        delay=10,
    )
    return app_name


def test_garm_configurator_waits_without_image_relation(
    juju: jubilant.Juju,
    garm_configurator_app: str,
) -> None:
    """
    arrange: garm-configurator charm deployed with valid mock configuration.
    act: Check the application status before any image builder is connected.
    assert: Application is Waiting — the image builder relation is required.
    """
    status = juju.status()
    assert jubilant.all_waiting(status, garm_configurator_app)


def test_garm_configurator_image_relation(
    juju: jubilant.Juju,
    garm_configurator_app: str,
    any_charm_image_builder_app: str,
) -> None:
    """
    arrange: garm-configurator fully configured, fake image builder deployed.
    act: Integrate garm-configurator:image with the fake image builder.
    assert:
      - garm-configurator unit relation data contains all six OpenStack credential fields.
      - fake image builder unit relation data contains the synthetic image UUID.
      - garm-configurator is Active once relation data has settled.
    """
    juju.integrate(
        f"{garm_configurator_app}:image",
        f"{any_charm_image_builder_app}:provide-github-runner-image-v0",
    )
    # The charm starts in WaitingStatus (no relation). ActiveStatus is only
    # reached after credentials are written AND the UUID is received back, so
    # all_active is a reliable signal that the full handshake completed.
    juju.wait(
        lambda status: jubilant.all_active(status, garm_configurator_app),
        timeout=5 * 60,
        delay=10,
    )

    configurator_unit = f"{garm_configurator_app}/0"
    builder_unit = f"{any_charm_image_builder_app}/0"

    builder_info = json.loads(
        juju.cli("show-unit", builder_unit, "--format=json")
    )[builder_unit]
    builder_rel = next(
        (r for r in builder_info["relation-info"]
         if r["endpoint"] == "provide-github-runner-image-v0"),
        None,
    )
    assert builder_rel is not None, "provide-github-runner-image-v0 relation not found in show-unit"
    creds = builder_rel["related-units"][configurator_unit]["data"]

    conf_info = json.loads(
        juju.cli("show-unit", configurator_unit, "--format=json")
    )[configurator_unit]
    conf_rel = next(
        (r for r in conf_info["relation-info"] if r["endpoint"] == "image"),
        None,
    )
    assert conf_rel is not None, "image relation not found in show-unit"
    uuid_data = conf_rel["related-units"][builder_unit]["data"]

    assert creds["auth_url"] == "https://keystone.example.com:5000/v3"
    assert creds["username"] == "admin"
    assert creds["password"] == "fake-password"
    assert creds["project_name"] == "myproject"
    assert creds["user_domain_name"] == "Default"
    assert creds["project_domain_name"] == "Default"

    assert uuid_data["id"] == "fake-openstack-image-uuid"
