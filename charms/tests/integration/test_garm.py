# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import json

import jubilant
import pytest

GARM_BINARY = "/usr/local/bin/garm"
GARM_PROVIDER_BINARY = "/usr/local/bin/garm-provider-openstack"
GARM_CONFIG_PATH = "/etc/garm/config.toml"
GARM_SECRETS_LABEL = "garm-secrets"


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
    result = juju.exec(unit, ["ls", GARM_BINARY, GARM_PROVIDER_BINARY])

    assert result.return_code == 0, (
        f"Expected GARM binaries at {GARM_BINARY} and {GARM_PROVIDER_BINARY}, "
        f"got: {result.stderr}"
    )


def test_garm_charm_reaches_active(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed with the built ROCK image and default config.
    act: Observe the Juju application status.
    assert: The application is in active status, confirming a successful install.
    """
    status = juju.status()

    assert jubilant.all_active(status, garm_app), (
        f"Expected {garm_app} to be active, got: "
        f"{status.apps[garm_app].app_status.current}"
    )


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
    result = juju.exec(unit, ["pebble", "plan"])

    assert result.return_code == 0, f"pebble plan failed: {result.stderr}"
    plan_output = result.stdout
    assert GARM_BINARY in plan_output, (
        f"Expected {GARM_BINARY} in pebble plan, got: {plan_output}"
    )
    assert f"-config {GARM_CONFIG_PATH}" in plan_output, (
        f"Expected '-config {GARM_CONFIG_PATH}' in pebble plan, got: {plan_output}"
    )


def test_garm_juju_secret_has_expected_keys(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed and active (leader has initialised secrets).
    act: List Juju secrets and show the garm-secrets secret content.
    assert: The garm-secrets secret contains both jwt-secret and db-passphrase keys.
    """
    secrets_json = juju.cli("secrets", "--format=json")
    secrets = json.loads(secrets_json)

    garm_secret_uri = None
    for uri, info in secrets.items():
        if info.get("label") == GARM_SECRETS_LABEL:
            garm_secret_uri = uri
            break

    assert garm_secret_uri is not None, (
        f"Expected a Juju secret labelled '{GARM_SECRETS_LABEL}' to exist"
    )

    secret_json = juju.cli("show-secret", "--reveal", "--format=json", garm_secret_uri)
    secret = json.loads(secret_json)
    content = secret[garm_secret_uri]["content"]["Data"]

    assert "jwt-secret" in content, (
        f"Expected 'jwt-secret' key in {GARM_SECRETS_LABEL}, got keys: {list(content)}"
    )
    assert "db-passphrase" in content, (
        f"Expected 'db-passphrase' key in {GARM_SECRETS_LABEL}, got keys: {list(content)}"
    )
