# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import json
import logging

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
GARM_ADMIN_CREDENTIALS_LABEL = "garm-admin-credentials"
GARM_API_PORT = 8080
PEBBLE_PREFIX = "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble"


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


def _get_admin_credentials(juju: jubilant.Juju) -> dict[str, str]:
    """Retrieve GARM admin credentials from the garm-admin-credentials Juju secret.

    Args:
        juju: Jubilant Juju handle.

    Returns:
        Dict with at least ``username`` and ``password`` keys as stored by the charm.
    """
    secrets_json = juju.cli("secrets", "--format=json")
    all_secrets = json.loads(secrets_json)
    admin_creds_uri = None
    for uri, info in all_secrets.items():
        if info.get("label") == GARM_ADMIN_CREDENTIALS_LABEL:
            admin_creds_uri = uri
            break
    assert (
        admin_creds_uri is not None
    ), f"Expected a Juju secret labelled '{GARM_ADMIN_CREDENTIALS_LABEL}' to exist"
    secret_json = juju.cli("show-secret", "--reveal", "--format=json", admin_creds_uri)
    secret = json.loads(secret_json)
    content = secret[admin_creds_uri]["content"]["Data"]
    for key in ("username", "password"):
        assert (
            key in content
        ), f"Expected '{key}' key in '{GARM_ADMIN_CREDENTIALS_LABEL}', got: {list(content)}"
    return content


def _garm_first_run(juju: jubilant.Juju, address: str) -> str:
    """Log in to GARM with charm-managed credentials and return an admin JWT.

    The charm creates the admin user automatically via _maybe_first_run().
    This function reads credentials from the garm-admin-credentials Juju secret,
    logs in to obtain a JWT, and configures required controller URLs so GARM will
    serve operational API endpoints.

    Retries with backoff to allow GARM time to finish starting and the charm's
    first-run initialization to complete.

    Args:
        juju: Jubilant Juju handle (used to read admin credentials from Juju secret).
        address: GARM unit IP address.

    Returns:
        JWT token string for authenticated API calls.
    """
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    creds = _get_admin_credentials(juju)

    session = requests.Session()
    retries = Retry(total=10, backoff_factor=2, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))

    class _LoginRetryable(Exception):
        pass

    @retry(
        retry=retry_if_exception_type(
            (requests.exceptions.ConnectionError, _LoginRetryable)
        ),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _do_login() -> str:
        resp = session.post(
            f"{base_url}/auth/login",
            json={"username": creds["username"], "password": creds["password"]},
            timeout=30,
        )
        logger.info(
            "login response: status=%d body=%s", resp.status_code, resp.text[:500]
        )
        if resp.status_code != 200:
            raise _LoginRetryable(
                f"Unexpected login status {resp.status_code}: {resp.text[:200]}"
            )
        token = resp.json().get("token", "")
        assert token, "Expected non-empty JWT token from login"
        return token

    token = _do_login()

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


class _MetricsNotReady(Exception):
    """Raised while GARM's /metrics is still warming up (retryable)."""


@retry(
    retry=retry_if_exception_type(
        (requests.exceptions.ConnectionError, _MetricsNotReady)
    ),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(10),
    reraise=True,
)
def _scrape_metrics_until_ready(metrics_url: str) -> requests.Response:
    """Scrape GARM's /metrics (no auth) and retry until the metrics are populated.

    garm_health is the reliable signal that GARM's own metrics (not just the Go
    runtime metrics) are exported: it is populated by an immediate collection at
    startup and refreshed every tick, so retry briefly to absorb that startup
    window. Other metric names are documented in GARM's monitoring spec.

    Args:
        metrics_url: Full URL of GARM's /metrics endpoint.

    Returns:
        The successful (HTTP 200) response, which contains garm_health.
    """
    # No Authorization header: a 200 proves JWT auth is disabled on /metrics.
    response = requests.get(metrics_url, timeout=30)
    # A 5xx may occur briefly while GARM is still warming up, so retry it. A 4xx
    # (e.g. 401/403 if auth were required, 404 for a wrong path) is a real
    # regression and must surface immediately rather than being masked as a
    # metrics-warm-up timeout.
    if response.status_code >= 500:
        raise _MetricsNotReady()
    assert response.status_code == requests.codes.ok, (
        f"Expected 200 without a JWT token, got {response.status_code}: "
        f"{response.text[:200]}"
    )
    if "garm_health" not in response.text:
        raise _MetricsNotReady()
    return response


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
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed with postgresql & garm-configurator integrated.
    act: Observe the Juju application status.
    assert: The application is in active status, confirming a successful install.
    """
    status = juju.status()
    current = status.apps[configurator_garm].app_status.current
    logger.info("GARM app status: %s", current)

    assert jubilant.all_active(
        status, configurator_garm
    ), f"Expected {configurator_garm} to be active, got: {current}"


def test_garm_api_controller_info(
    juju: jubilant.Juju,
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed, active, and connected to postgresql.
    act: Complete first-run initialization and query /api/v1/controller-info.
    assert: The controller info response contains a valid controller_id (UUID),
        proving that GARM started, ran DB migrations, and is serving API requests.
    """
    address = _get_garm_address(juju, configurator_garm)
    logger.info("GARM address: %s", address)

    token = _garm_first_run(juju, address)
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
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed, active, and initialized with an admin user.
    act: Query GET /api/v1/scalesets to list scale sets.
    assert: The API returns a successful response (empty list), proving the
        scale set query path through postgresql is functional.
    """
    address = _get_garm_address(juju, configurator_garm)
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
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed with the OpenStack provider configured.
    act: Query GET /api/v1/providers to list available providers.
    assert: The openstack provider is registered and visible through the API.
    """
    address = _get_garm_address(juju, configurator_garm)
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
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed and active.
    act: Read the Pebble plan from the workload container.
    assert: The Pebble service runs the GARM binary with the canonical config flag.
    """
    unit = f"{configurator_garm}/0"
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


def test_garm_secrets_juju_secret_has_expected_keys(
    juju: jubilant.Juju,
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed and active (leader has initialised secrets).
    act: List Juju secrets and show the garm-secrets secret content.
    assert: The garm-secrets secret contains jwt-secret and db-passphrase keys.
    """
    logger.info("Listing Juju secrets")
    secrets_json = juju.cli("secrets", "--format=json")
    all_secrets = json.loads(secrets_json)

    garm_secret_uri = None
    for uri, info in all_secrets.items():
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


def test_garm_admin_credentials_juju_secret_has_expected_keys(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed and active (leader has initialised secrets).
    act: List Juju secrets and show the garm-admin-credentials secret content.
    assert: The garm-admin-credentials secret contains username, password, email,
        and full-name keys.
    """
    logger.info("Listing Juju secrets")
    secrets_json = juju.cli("secrets", "--format=json")
    all_secrets = json.loads(secrets_json)

    admin_creds_uri = None
    for uri, info in all_secrets.items():
        if info.get("label") == GARM_ADMIN_CREDENTIALS_LABEL:
            admin_creds_uri = uri
            break

    logger.info("Found admin credentials secret URI: %s", admin_creds_uri)
    assert (
        admin_creds_uri is not None
    ), f"Expected a Juju secret labelled '{GARM_ADMIN_CREDENTIALS_LABEL}' to exist"

    admin_json = juju.cli("show-secret", "--reveal", "--format=json", admin_creds_uri)
    admin_secret = json.loads(admin_json)
    admin_content = admin_secret[admin_creds_uri]["content"]["Data"]
    logger.info("GARM admin credentials keys: %s", list(admin_content))

    for expected_key in ("username", "password", "email", "full-name"):
        assert expected_key in admin_content, (
            f"Expected '{expected_key}' key in {GARM_ADMIN_CREDENTIALS_LABEL},"
            f" got keys: {list(admin_content)}"
        )


def test_garm_metrics_endpoint_no_auth(
    juju: jubilant.Juju,
    configurator_garm: str,
):
    """
    arrange: The GARM charm is deployed, active, and connected to postgresql.
    act: GET /metrics with no Authorization header.
    assert: The endpoint responds 200 (JWT auth disabled) and exposes GARM metrics.
    """
    address = _get_garm_address(juju, configurator_garm)
    metrics_url = f"http://{address}:{GARM_API_PORT}/metrics"
    logger.info("Scraping GARM metrics (no auth) at %s", metrics_url)

    resp = _scrape_metrics_until_ready(metrics_url)
    # _scrape_metrics_until_ready only returns on a 200 response containing garm_health.
    assert "garm_health" in resp.text, (
        "Expected the garm_health metric in the /metrics response; "
        f"got first 500 chars: {resp.text[:500]}"
    )


def test_garm_api_has_configurator_provider(
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
    assert any(n.startswith("garm-configurator") for n in api_provider_names), (
        f"Expected a 'garm-configurator-*' provider in GARM API, "
        f"got: {api_provider_names}"
    )
