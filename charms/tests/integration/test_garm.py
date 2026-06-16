# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import json
import logging
import secrets

import jubilant
import pytest
import requests
from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

GARM_BINARY = "/usr/local/bin/garm"
GARM_PROVIDER_BINARY = "/usr/local/bin/garm-provider-openstack"
GARM_CONFIG_PATH = "/etc/garm/config.toml"
GARM_SECRETS_LABEL = "garm-secrets"
GARM_API_PORT = 9997
PEBBLE_PREFIX = "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble"

# Generated once per session so all test functions that call _garm_first_run use
# the same credentials. Format guarantees GARM's strong-password requirements:
# uppercase (A), lowercase (dmin + hex), digit (1 + hex), symbols (-, !).
_GARM_ADMIN_PASSWORD = f"Admin-{secrets.token_hex(8)}-X1!"


def _pebble_exec(juju: jubilant.Juju, unit: str, command: str) -> jubilant.Task:
    """Run a command inside the workload container via pebble exec.

    Args:
        juju: Jubilant Juju handle.
        unit: Unit name (e.g. "github-runner-garm/0").
        command: Shell command to execute inside the container.

    Returns:
        ExecResult with stdout/stderr.
    """
    return juju.exec(f"{PEBBLE_PREFIX} exec -- {command}", unit=unit)


def _get_garm_address(juju: jubilant.Juju, app_name: str) -> str:
    """Get the IP address of the GARM unit.

    Args:
        juju: Jubilant Juju handle.
        app_name: GARM application name.

    Returns:
        IP address string.
    """
    status = juju.status()
    unit_name = f"{app_name}/0"
    return status.apps[app_name].units[unit_name].address


def _garm_first_run(address: str) -> str:
    """Complete GARM first-run initialization and return an admin JWT.

    Calls /api/v1/first-run to create the initial admin user, then logs in
    to obtain a JWT. Also configures required controller URLs so GARM will
    serve operational API endpoints.

    Retries with backoff to allow GARM time to finish starting after replan.

    Args:
        address: GARM unit IP address.

    Returns:
        JWT token string for authenticated API calls.
    """
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    # GARM v0.2.x requires strong passwords (min 12 chars, mixed case, digits, symbols)
    password = _GARM_ADMIN_PASSWORD
    first_run_payload = {
        "username": "admin",
        "password": password,
        "email": "admin@test.local",
        "full_name": "Integration Test Admin",
    }

    session = requests.Session()
    retries = Retry(total=10, backoff_factor=2, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))

    class _FirstRunRetryable(Exception):
        pass

    @retry(
        retry=retry_if_exception_type(
            (requests.exceptions.ConnectionError, _FirstRunRetryable)
        ),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _post_first_run() -> None:
        resp = session.post(f"{base_url}/first-run", json=first_run_payload, timeout=30)
        logger.info(
            "first-run response: status=%d body=%s", resp.status_code, resp.text[:500]
        )
        if resp.status_code not in (200, 409):
            # 200 = user created, 409 = already initialized — either way, done
            raise _FirstRunRetryable(
                f"Unexpected status {resp.status_code}: {resp.text[:200]}"
            )

    _post_first_run()

    # Login to obtain JWT
    login_payload = {"username": "admin", "password": password}
    resp = session.post(f"{base_url}/auth/login", json=login_payload, timeout=30)
    logger.info("login response: status=%d body=%s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    token = resp.json().get("token", "")
    assert token, "Expected non-empty JWT token from login"

    # Configure controller URLs — GARM requires metadata_url and callback_url
    # before it will serve operational endpoints (returns 409 otherwise)
    headers = {"Authorization": f"Bearer {token}"}
    controller_payload = {
        "metadata_url": f"http://{address}:{GARM_API_PORT}/api/v1/metadata",
        "callback_url": f"http://{address}:{GARM_API_PORT}/api/v1/callbacks",
        "webhook_url": f"http://{address}:{GARM_API_PORT}/webhooks",
    }
    resp = session.put(
        f"{base_url}/controller", json=controller_payload, headers=headers, timeout=30
    )
    logger.info(
        "controller setup response: status=%d body=%s",
        resp.status_code,
        resp.text[:300],
    )
    resp.raise_for_status()

    return token


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
        f"{PEBBLE_PREFIX} ls /usr/local/bin/",
        unit=unit,
    )

    assert (
        GARM_BINARY.split("/")[-1] in result.stdout
    ), f"Expected garm binary in /usr/local/bin/, got: {result.stdout}"
    assert (
        GARM_PROVIDER_BINARY.split("/")[-1] in result.stdout
    ), f"Expected garm-provider-openstack binary in /usr/local/bin/, got: {result.stdout}"
    logger.info("GARM binaries confirmed present: %s", result.stdout.strip())


def test_garm_version(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed and active.
    act: Run `garm -version` inside the workload container.
    assert: The command exits successfully and prints a version string.
    """
    unit = f"{garm_app}/0"
    logger.info("Running garm -version in unit %s", unit)
    result = _pebble_exec(juju, unit, f"{GARM_BINARY} -version")

    version_output = result.stdout.strip()
    logger.info("GARM version: %s", version_output)
    assert version_output, "Expected non-empty version output from garm -version"
    # TODO: Once garm-rockcraft.yaml switches from source-commit to source-tag (>= v0.2.2),
    # tighten this assertion to require version_output.startswith("v").
    # Currently the ROCK is built from a shallow clone of a pinned commit, so git describe
    # falls back to an abbreviated SHA (e.g. "47811d0") instead of a semver tag.
    is_semver = version_output.startswith("v") or "." in version_output
    is_commit_sha = all(c in "0123456789abcdef" for c in version_output)
    assert (
        is_semver or is_commit_sha
    ), f"Expected version string (semver or commit SHA), got: {version_output}"


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


def test_garm_api_controller_info(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed, active, and connected to postgresql.
    act: Complete first-run initialization and query /api/v1/controller-info.
    assert: The controller info response contains a valid controller_id (UUID),
        proving that GARM started, ran DB migrations, and is serving API requests.
    """
    address = _get_garm_address(juju, garm_app)
    logger.info("GARM address: %s", address)

    token = _garm_first_run(address)
    assert token, "Expected non-empty JWT token from first-run/login"
    logger.info("Got admin JWT token (length=%d)", len(token))

    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/controller-info", headers=headers, timeout=30)
    resp.raise_for_status()

    info = resp.json()
    logger.info("Controller info: %s", json.dumps(info, indent=2))
    assert "controller_id" in info, f"Expected controller_id in response, got: {info}"
    assert info["controller_id"], "Expected non-empty controller_id"


def test_garm_api_list_scalesets(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed, active, and initialized with an admin user.
    act: Query GET /api/v1/scalesets to list scale sets.
    assert: The API returns a successful response (empty list), proving the
        scale set query path through postgresql is functional.
    """
    address = _get_garm_address(juju, garm_app)
    token = _garm_first_run(address)

    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/scalesets", headers=headers, timeout=30)
    resp.raise_for_status()

    scalesets = resp.json()
    logger.info("Scale sets response: %s", scalesets)
    # Fresh GARM has no scale sets configured — expect empty list
    assert isinstance(
        scalesets, list
    ), f"Expected list response, got: {type(scalesets)}"
    assert (
        len(scalesets) == 0
    ), f"Expected empty scale set list on fresh GARM, got: {scalesets}"


def test_garm_api_list_providers(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed with the OpenStack provider configured.
    act: Query GET /api/v1/providers to list available providers.
    assert: The openstack provider is registered and visible through the API.
    """
    address = _get_garm_address(juju, garm_app)
    token = _garm_first_run(address)

    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/providers", headers=headers, timeout=30)
    resp.raise_for_status()

    providers = resp.json()
    logger.info("Providers response: %s", json.dumps(providers, indent=2))
    assert isinstance(
        providers, list
    ), f"Expected list response, got: {type(providers)}"
    provider_names = [p.get("name", "") for p in providers]
    assert (
        "openstack" in provider_names
    ), f"Expected 'openstack' provider in list, got: {provider_names}"


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
        f"{PEBBLE_PREFIX} plan",
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


def test_garm_toml_has_configurator_provider(
    juju: jubilant.Juju,
    configurator_garm: str,
):
    """
    arrange: Configurator with OpenStack config is integrated with GARM.
    act: Query the GARM REST API for registered providers.
    assert: A provider named 'garm-configurator-*' is registered and visible
        via the GARM API, confirming the configurator relation data was
        consumed and the provider was loaded.
    """
    address = _get_garm_address(juju, configurator_garm)
    token = _garm_first_run(address)
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/providers", headers=headers, timeout=30)
    resp.raise_for_status()
    api_providers = resp.json()
    logger.info("Providers response: %s", json.dumps(api_providers, indent=2))
    assert isinstance(
        api_providers, list
    ), f"Expected list response from GARM API, got: {type(api_providers)}"
    api_provider_names = [p.get("name", "") for p in api_providers]
    assert any(
        n.startswith("garm-configurator") for n in api_provider_names
    ), (
        f"Expected a 'garm-configurator-*' provider in GARM API, "
        f"got: {api_provider_names}"
    )
