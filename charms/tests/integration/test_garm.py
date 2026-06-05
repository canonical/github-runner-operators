# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import json
import logging

import jubilant
import pytest

logger = logging.getLogger(__name__)

GARM_BINARY = "/usr/local/bin/garm"
GARM_PROVIDER_BINARY = "/usr/local/bin/garm-provider-openstack"
GARM_CONFIG_PATH = "/etc/garm/config.toml"
GARM_SECRETS_LABEL = "garm-secrets"


def test_garm_blocks_without_postgresql(
    juju: jubilant.Juju,
    garm_app_deployed: str,
):
    """
    arrange: The GARM charm is deployed without postgresql integration.
    act: Observe the Juju application status.
    assert: The application is blocked with a message about missing postgresql.
    """
    status = juju.status()
    app_status = status.apps[garm_app_deployed].app_status
    logger.info(
        "GARM status without postgresql: %s - %s",
        app_status.current,
        app_status.message,
    )

    assert app_status.current == "blocked"
    assert "postgresql" in app_status.message.lower()


def test_garm_rock_contains_binaries(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed with the built ROCK image.
    act: Execute a file-existence check for GARM binaries inside the workload container.
    assert: Both the GARM server binary and the OpenStack provider binary are present.
    """
    unit = f"{garm_app}/0"
    logger.info("Checking GARM binaries in unit %s", unit)
    result = juju.exec(
        f"PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble ls /usr/local/bin/",
        unit=unit,
    )

    assert (
        GARM_BINARY.split("/")[-1] in result.stdout
    ), f"Expected garm binary in /usr/local/bin/, got: {result.stdout}"
    assert (
        GARM_PROVIDER_BINARY.split("/")[-1] in result.stdout
    ), f"Expected garm-provider-openstack binary in /usr/local/bin/, got: {result.stdout}"
    logger.info("GARM binaries confirmed present: %s", result.stdout.strip())


def test_garm_charm_reaches_active(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed with postgresql integrated.
    act: Observe the Juju application status.
    assert: The application is in active status, confirming a successful install.
    """
    status = juju.status()
    current = status.apps[garm_app].app_status.current
    logger.info("GARM app status: %s", current)

    assert jubilant.all_active(
        status, garm_app
    ), f"Expected {garm_app} to be active, got: {current}"


def test_garm_pebble_service_command(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed and active.
    act: Read the Pebble plan from the workload container.
    assert: The Pebble service runs the GARM binary with the canonical config flag.
    """
    unit = f"{garm_app}/0"
    logger.info("Reading Pebble plan from unit %s", unit)
    result = juju.exec(
        "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble plan",
        unit=unit,
    )
    plan_output = result.stdout
    logger.info("Pebble plan:\n%s", plan_output)
    assert (
        GARM_BINARY in plan_output
    ), f"Expected {GARM_BINARY} in pebble plan, got: {plan_output}"
    assert (
        f"-config {GARM_CONFIG_PATH}" in plan_output
    ), f"Expected '-config {GARM_CONFIG_PATH}' in pebble plan, got: {plan_output}"


def test_garm_juju_secret_has_expected_keys(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed and active (leader has initialised secrets).
    act: List Juju secrets and show the garm-secrets secret content.
    assert: The garm-secrets secret contains jwt-secret and db-passphrase keys.
    """
    logger.info("Listing Juju secrets to find '%s'", GARM_SECRETS_LABEL)
    secrets_json = juju.cli("secrets", "--format=json")
    secrets = json.loads(secrets_json)

    garm_secret_uri = None
    for uri, info in secrets.items():
        if info.get("label") == GARM_SECRETS_LABEL:
            garm_secret_uri = uri
            break

    logger.info("Found GARM secret URI: %s", garm_secret_uri)
    assert (
        garm_secret_uri is not None
    ), f"Expected a Juju secret labelled '{GARM_SECRETS_LABEL}' to exist"

    secret_json = juju.cli("show-secret", "--reveal", "--format=json", garm_secret_uri)
    secret = json.loads(secret_json)
    content = secret[garm_secret_uri]["content"]["Data"]
    logger.info("GARM secret keys: %s", list(content))

    assert (
        "jwt-secret" in content
    ), f"Expected 'jwt-secret' key in {GARM_SECRETS_LABEL}, got keys: {list(content)}"
    assert (
        "db-passphrase" in content
    ), f"Expected 'db-passphrase' key in {GARM_SECRETS_LABEL}, got keys: {list(content)}"


def test_garm_config_uses_postgresql_backend(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed with postgresql integrated.
    act: Read the GARM config TOML from the workload container.
    assert: The config uses the postgresql backend with the expected fields.
    """
    unit = f"{garm_app}/0"
    logger.info("Reading GARM config from unit %s", unit)
    result = juju.exec(
        f"PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble exec cat {GARM_CONFIG_PATH}",
        unit=unit,
    )
    config_content = result.stdout
    logger.info("GARM config:\n%s", config_content)

    # Verify postgresql backend is configured
    assert (
        'backend = "postgresql"' in config_content
    ), f"Expected postgresql backend in config, got:\n{config_content}"
    assert (
        "[database.postgresql]" in config_content
    ), f"Expected [database.postgresql] section in config, got:\n{config_content}"
    # Verify no sqlite3 references
    assert (
        "sqlite3" not in config_content
    ), f"Expected no sqlite3 references in config, got:\n{config_content}"
    # Verify passphrase is present
    assert (
        "passphrase" in config_content
    ), f"Expected passphrase in [database] section, got:\n{config_content}"
