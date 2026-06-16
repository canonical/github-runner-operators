# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import base64
import json
import logging
import secrets
import shlex
import urllib.error
import urllib.request

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
GARM_API_PORT = 8080
PEBBLE_PREFIX = "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble"

# Generated once per session so all test functions that call _garm_first_run use
# the same credentials. Format guarantees GARM's strong-password requirements:
# uppercase (A), lowercase (dmin + hex), digit (1 + hex), symbols (-, !).
_GARM_ADMIN_PASSWORD = f"Admin-{secrets.token_hex(8)}-X1!"
_SCALESET_TEST_NAME = "test-scaleset"
_SCALESET_TEST_CREDENTIAL_NAME = "github-app-12345"

_TEST_RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICXwIBAAKBgQC2tCW5B18y5VnqqokOeamJgasI3H1405WWv7FmWl31I1Cgabhi
MFcHdNECXFUC3wtqo/bXyCQbANRBkpZudJfSGos3+1iOJK1fd+MU8ntHVtgpvb5j
whdFSVJ9EL4/2u0K0S+fIyilD9q7K5mhk0MYLYWumPIRLkbtwr9a7LgY5wIDAQAB
AoGBAKIQGCoRjPNjmCfdT6fEaYtstt8sXiwQWu+WaHDnFdL9mWZBgOmwAXK+vyt9
5XafjMvyV2I+yTAewyjLM58U0xlslJu6Bk0Zw920sTmK9Qvvq/2mjsqw+PWr9rRx
qZFDCefAlB0Npo9tXHAf3ec5+vlm4QsEl6dty+Wx6aSHHMRpAkEA8e5IwkJZFcWO
aCc8Z+cnoidomlkvGlruncXMG1KhisQTleQVc1bM8tIZq2nNUG1zKJqHeCacQLiV
LKALnZDSCwJBAMFUIHd7ikYaAgTvrAKmzOZlMKVuGr2SHPODWoaWkEagEsrOw+H2
PYonSYkbzPyXH6iKUOhWH+ZA1r6K1lhdWhUCQQCquaTOsVN8cbVU+ps+F3l4jKbc
hSMgThsla3flsCIfcs7/b71Tb2Wh1XIX7Mnef95MQQBoYZbSdW+P1kFcJ96RAkEA
oSyuqI4BGDJkjpL1l3xSBJ5F8RUbDAI9SrKujNgHTinzoMrCOabdZUkdoEXiHo8r
IIq3qwrqKz7RCSecTSz+hQJBAJDKODanbnrPxNDgmIp52BMtiYI4vv7gKp/MSW0N
PG8an+PHNVGDEj1cOOwp/YNQieRp/WPH6bpBtwwe0r6pQZQ=
-----END RSA PRIVATE KEY-----"""


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


def garm_login_from_secret(juju: jubilant.Juju, garm_app_name: str, garm_url: str) -> str:
    """Log into the GARM API using admin credentials stored in Juju secrets."""
    secrets_json = juju.cli("secrets", "--format=json")
    all_secrets = json.loads(secrets_json)
    garm_secret_uri = next(
        (uri for uri, info in all_secrets.items() if info.get("label") == GARM_SECRETS_LABEL),
        None,
    )
    assert garm_secret_uri, f"{GARM_SECRETS_LABEL} not found for {garm_app_name}"

    secret_json = juju.cli("show-secret", "--reveal", "--format=json", garm_secret_uri)
    secret_data = json.loads(secret_json)
    content = secret_data[garm_secret_uri]["content"]["Data"]
    admin_username = content["admin-username"]
    admin_password = content["admin-password"]

    base_url = garm_url.rstrip("/")
    if not base_url.endswith("/api/v1"):
        base_url = f"{base_url}/api/v1"

    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": admin_username, "password": admin_password},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("token", "")
    assert token, "Expected non-empty JWT token from GARM login"
    return token


class _MetricsNotReady(Exception):
    """Raised while GARM's /metrics is still warming up (retryable)."""


@retry(
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, _MetricsNotReady)),
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

def _garm_api_base_url(address: str) -> str:
    """Return the GARM v1 API base URL for a unit address."""
    return f"http://{address}:{GARM_API_PORT}/api/v1"


def _garm_auth_headers(token: str) -> dict[str, str]:
    """Return authorization headers for GARM API requests."""
    return {"Authorization": f"Bearer {token}"}


def _list_scalesets(base_url: str, token: str) -> list[dict]:
    """List GARM scalesets via the REST API."""
    resp = requests.get(f"{base_url}/scalesets", headers=_garm_auth_headers(token), timeout=30)
    resp.raise_for_status()
    scalesets = resp.json()
    assert isinstance(scalesets, list), f"Expected list response, got: {type(scalesets)}"
    return scalesets


def _list_providers(base_url: str, token: str) -> list[dict]:
    """List GARM providers via the REST API."""
    resp = requests.get(f"{base_url}/providers", headers=_garm_auth_headers(token), timeout=30)
    resp.raise_for_status()
    providers = resp.json()
    assert isinstance(providers, list), f"Expected list response, got: {type(providers)}"
    return providers


def _find_scaleset(scalesets: list[dict], name: str) -> dict | None:
    """Return the first scaleset with the requested name."""
    return next((scaleset for scaleset in scalesets if scaleset.get("name") == name), None)


def _get_relation_info(juju: jubilant.Juju, unit: str, endpoint: str, related_app: str) -> dict:
    """Return show-unit relation info for a specific endpoint and related app."""
    unit_info = json.loads(juju.cli("show-unit", unit, "--format=json"))[unit]
    for relation in unit_info["relation-info"]:
        if relation["endpoint"] != endpoint:
            continue
        related_units = relation.get("related-units", {})
        if any(name.startswith(f"{related_app}/") for name in related_units):
            return relation
    raise AssertionError(
        f"Relation {endpoint!r} between {unit!r} and app {related_app!r} not found"
    )


def _relation_exists(juju: jubilant.Juju, app_name: str, related_app: str) -> bool:
    """Return whether the GARM app is related to the configurator app."""
    try:
        _get_relation_info(juju, f"{app_name}/0", "garm-configurator", related_app)
    except AssertionError:
        return False
    return True


def _get_scaleset_relation_data(
    juju: jubilant.Juju, garm_app: str, garm_configurator_for_scaleset_tests: str
) -> dict[str, str]:
    """Return the configurator unit relation data as seen from the GARM side."""
    relation = _get_relation_info(
        juju,
        f"{garm_app}/0",
        "garm-configurator",
        garm_configurator_for_scaleset_tests,
    )
    related_unit = f"{garm_configurator_for_scaleset_tests}/0"
    data = relation["related-units"][related_unit]["data"]
    return {key: str(value) for key, value in data.items()}


def _ensure_garm_configurator_relation(
    juju: jubilant.Juju, garm_app: str, garm_configurator_for_scaleset_tests: str
) -> None:
    """Ensure the GARM app is integrated with the scaleset-test configurator."""
    if not _relation_exists(juju, garm_app, garm_configurator_for_scaleset_tests):
        juju.integrate(garm_app, garm_configurator_for_scaleset_tests)
    juju.wait(
        lambda status: jubilant.all_active(status, garm_app),
        timeout=3 * 60,
        delay=10,
    )


def _set_scaleset_relation_data(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
    **overrides: str,
) -> None:
    """Mutate configurator relation data to exercise GARM reconcile scenarios."""
    unit = f"{garm_configurator_for_scaleset_tests}/0"
    relation = _get_relation_info(juju, unit, "garm-configurator", garm_app)
    relation_id = relation["relation-id"]
    relation_data = _get_scaleset_relation_data(
        juju, garm_app, garm_configurator_for_scaleset_tests
    )
    relation_data.update(overrides)
    command = " ".join(
        [
            "relation-set",
            "-r",
            str(relation_id),
            *[shlex.quote(f"{key}={value}") for key, value in relation_data.items()],
        ]
    )
    juju.exec(command, unit=unit)
    juju.wait(
        lambda status: jubilant.all_active(status, garm_app),
        timeout=3 * 60,
        delay=10,
    )


def _create_test_credential(garm_url: str, token: str) -> str:
    """Create a GitHub App credential in GARM for testing."""

    def _request(
        path: str, payload: dict, *, method: str = "POST", allow_conflict: bool = True
    ) -> dict | None:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{garm_url}{path}",
            data=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            if allow_conflict and exc.code == 409:
                return None
            raise

    try:
        _request(
            "/github/endpoints",
            {
                "name": "github.com",
                "description": "GitHub.com test endpoint",
                "base_url": "https://github.com",
                "api_base_url": "https://api.github.com",
                "upload_base_url": "https://uploads.github.com",
            },
        )
        _request(
            "/github/credentials",
            {
                "name": _SCALESET_TEST_CREDENTIAL_NAME,
                "description": "Test credential for scaleset integration tests",
                "endpoint": "github.com",
                "auth_type": "app",
                "app": {
                    "app_id": 12345,
                    "installation_id": 67890,
                    "private_key_bytes": base64.b64encode(
                        _TEST_RSA_PRIVATE_KEY.encode()
                    ).decode(),
                },
            },
        )
    except urllib.error.HTTPError:
        _request(
            "/credentials",
            {
                "name": _SCALESET_TEST_CREDENTIAL_NAME,
                "description": "Test credential for scaleset integration tests",
                "base_url": "https://github.com",
                "api_base_url": "https://api.github.com",
                "upload_base_url": "https://uploads.github.com",
                "ca_cert_bundle": "",
                "credentials": {
                    "name": "test-creds",
                    "description": "test",
                    "type": "github_app",
                    "payload": {
                        "app_id": 12345,
                        "installation_id": 67890,
                        "private_key": _TEST_RSA_PRIVATE_KEY,
                    },
                },
            },
            allow_conflict=True,
        )
    return _SCALESET_TEST_CREDENTIAL_NAME


@retry(
    retry=retry_if_exception_type((AssertionError, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(18),
    reraise=True,
)
def _wait_for_scaleset(
    base_url: str,
    token: str,
    name: str,
    *,
    image_id: str | None = None,
) -> dict:
    """Wait until a named scaleset exists and optionally reflects a new image."""
    scaleset = _find_scaleset(_list_scalesets(base_url, token), name)
    assert scaleset is not None, f"Expected scaleset {name!r} to exist"
    if image_id is not None:
        observed_image = scaleset.get("image_id") or scaleset.get("image")
        assert observed_image == image_id, (
            f"Expected scaleset {name!r} image/image_id to be {image_id!r}, "
            f"got {observed_image!r}"
        )
    return scaleset


@retry(
    retry=retry_if_exception_type((AssertionError, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(18),
    reraise=True,
)
def _wait_for_scaleset_absent(base_url: str, token: str, name: str) -> None:
    """Wait until a named scaleset no longer exists."""
    scaleset = _find_scaleset(_list_scalesets(base_url, token), name)
    assert scaleset is None, f"Expected scaleset {name!r} to be absent, got: {scaleset}"


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


def test_garm_metrics_endpoint_no_auth(
    juju: jubilant.Juju,
    garm_app: str,
):
    """
    arrange: The GARM charm is deployed, active, and connected to postgresql.
    act: GET /metrics with no Authorization header.
    assert: The endpoint responds 200 (JWT auth disabled) and exposes GARM metrics.
    """
    address = _get_garm_address(juju, garm_app)
    metrics_url = f"http://{address}:{GARM_API_PORT}/metrics"
    logger.info("Scraping GARM metrics (no auth) at %s", metrics_url)

    resp = _scrape_metrics_until_ready(metrics_url)
    # _scrape_metrics_until_ready only returns on a 200 response containing garm_health.
    assert "garm_health" in resp.text, (
        "Expected the garm_health metric in the /metrics response; "
        f"got first 500 chars: {resp.text[:500]}"
    )


def test_scaleset_creation_deferred_when_provider_missing(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: GARM and the test configurator are deployed, and a matching credential exists.
    act: Override the relation data with a provider name GARM does not know about.
    assert: No scaleset is created and the GARM app remains healthy.
    """
    _ensure_garm_configurator_relation(juju, garm_app, garm_configurator_for_scaleset_tests)
    address = _get_garm_address(juju, garm_app)
    base_url = _garm_api_base_url(address)
    token = garm_login_from_secret(juju, garm_app, base_url)
    _create_test_credential(base_url, token)
    _set_scaleset_relation_data(
        juju,
        garm_app,
        garm_configurator_for_scaleset_tests,
        provider_name="missing-provider",
    )

    _wait_for_scaleset_absent(base_url, token, _SCALESET_TEST_NAME)

    status = juju.status()
    app_status = status.apps[garm_app].app_status.current
    assert app_status in ("active", "waiting"), f"Expected active/waiting, got {app_status}"


def test_scalesets_created_from_relation_data(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: GARM is active and receives valid scaleset relation data plus a test credential.
    act: Reconcile against relation data that points at the built-in openstack provider.
    assert: A matching scaleset appears in the GARM API.
    """
    _ensure_garm_configurator_relation(juju, garm_app, garm_configurator_for_scaleset_tests)
    address = _get_garm_address(juju, garm_app)
    base_url = _garm_api_base_url(address)
    token = garm_login_from_secret(juju, garm_app, base_url)
    _create_test_credential(base_url, token)
    relation_data = _get_scaleset_relation_data(
        juju, garm_app, garm_configurator_for_scaleset_tests
    )
    provider_names = {provider.get("name", "") for provider in _list_providers(base_url, token)}
    provider_name = relation_data["provider_name"]
    if provider_name not in provider_names:
        pytest.skip(
            f"requires GARM provider {provider_name!r}; available providers: {sorted(provider_names)}"
        )
    _set_scaleset_relation_data(
        juju,
        garm_app,
        garm_configurator_for_scaleset_tests,
        min_idle_runner="1",
    )

    scaleset = _wait_for_scaleset(base_url, token, _SCALESET_TEST_NAME)
    assert scaleset["name"] == _SCALESET_TEST_NAME


def test_scaleset_updated_on_relation_change(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: A scaleset already exists in GARM from valid configurator relation data.
    act: Change the relation data image_id and wait for another reconcile.
    assert: The scaleset reflects the updated image_id.
    """
    _ensure_garm_configurator_relation(juju, garm_app, garm_configurator_for_scaleset_tests)
    address = _get_garm_address(juju, garm_app)
    base_url = _garm_api_base_url(address)
    token = garm_login_from_secret(juju, garm_app, base_url)
    _create_test_credential(base_url, token)
    relation_data = _get_scaleset_relation_data(
        juju, garm_app, garm_configurator_for_scaleset_tests
    )
    provider_names = {provider.get("name", "") for provider in _list_providers(base_url, token)}
    provider_name = relation_data["provider_name"]
    if provider_name not in provider_names:
        pytest.skip(
            f"requires GARM provider {provider_name!r}; available providers: {sorted(provider_names)}"
        )
    original_image_id = relation_data["image_id"]
    _set_scaleset_relation_data(
        juju,
        garm_app,
        garm_configurator_for_scaleset_tests,
        min_idle_runner="1",
    )
    _wait_for_scaleset(base_url, token, _SCALESET_TEST_NAME)

    _set_scaleset_relation_data(
        juju,
        garm_app,
        garm_configurator_for_scaleset_tests,
        image_id=f"{original_image_id}-updated",
    )

    scaleset = _wait_for_scaleset(
        base_url,
        token,
        _SCALESET_TEST_NAME,
        image_id=f"{original_image_id}-updated",
    )
    observed_image = scaleset.get("image_id") or scaleset.get("image")
    assert observed_image == f"{original_image_id}-updated"


def test_scaleset_deleted_when_relation_removed(
    juju: jubilant.Juju,
    garm_app: str,
    garm_configurator_for_scaleset_tests: str,
):
    """
    arrange: A scaleset exists in GARM for the test configurator relation.
    act: Remove the garm-configurator relation from GARM.
    assert: The matching scaleset disappears from GARM.
    """
    _ensure_garm_configurator_relation(juju, garm_app, garm_configurator_for_scaleset_tests)
    address = _get_garm_address(juju, garm_app)
    base_url = _garm_api_base_url(address)
    token = garm_login_from_secret(juju, garm_app, base_url)
    _create_test_credential(base_url, token)
    relation_data = _get_scaleset_relation_data(
        juju, garm_app, garm_configurator_for_scaleset_tests
    )
    provider_names = {provider.get("name", "") for provider in _list_providers(base_url, token)}
    provider_name = relation_data["provider_name"]
    if provider_name not in provider_names:
        pytest.skip(
            f"requires GARM provider {provider_name!r}; available providers: {sorted(provider_names)}"
        )
    _set_scaleset_relation_data(
        juju,
        garm_app,
        garm_configurator_for_scaleset_tests,
        min_idle_runner="1",
    )
    _wait_for_scaleset(base_url, token, _SCALESET_TEST_NAME)

    juju.remove_relation(garm_app, garm_configurator_for_scaleset_tests)
    juju.wait(
        lambda status: jubilant.all_active(status, garm_app),
        timeout=3 * 60,
        delay=10,
    )

    _wait_for_scaleset_absent(base_url, token, _SCALESET_TEST_NAME)
