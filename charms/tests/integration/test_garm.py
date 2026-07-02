# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import base64
import json
import logging
import secrets
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

from tests.integration.helpers import TEST_RSA_PRIVATE_KEY as _TEST_RSA_PRIVATE_KEY

logger = logging.getLogger(__name__)

GARM_BINARY = "/usr/local/bin/garm"
GARM_PROVIDER_BINARY = "/usr/local/bin/garm-provider-openstack"
GARM_CONFIG_PATH = "/etc/garm/config.toml"
GARM_SECRETS_LABEL = "garm-secrets"
GARM_ADMIN_CREDENTIALS_LABEL = "garm-admin-credentials"
GARM_API_PORT = 8080
PEBBLE_PREFIX = "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble"

# Generated once per session so all test functions that call _garm_first_run use
# the same credentials. Format guarantees GARM's strong-password requirements:
# uppercase (A), lowercase (dmin + hex), digit (1 + hex), symbols (-, !).
_GARM_ADMIN_PASSWORD = f"Admin-{secrets.token_hex(8)}-X1!"
_SCALESET_TEST_NAME = "test-scaleset"
_SCALESET_TEST_CREDENTIAL_NAME = "github-app-12345"
# Credential name the GARM charm derives from the configurator's github-app-id +
# installation id (12345 / 67890).
_SYNCED_CREDENTIAL_NAME = "app-12345-67890"


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

    Note: the unit workload status may be ``waiting`` at this point because
    _reconcile_runners() runs on integration and fails until first-run
    initialises GARM via the API.  The app-level status is what paas_charm
    sets, confirming the service is up.
    """
    status = juju.status()
    current = status.apps[configurator_garm].app_status.current
    logger.info("GARM app status: %s", current)

    assert current == "active", f"Expected {configurator_garm} to be active, got: {current}"


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
    token = _garm_first_run(juju, address)

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


def test_charm_registers_org_via_reconciler(
    juju: jubilant.Juju,
    configurator_garm: str,
    configurator_with_image: str,
):
    """
    arrange: GARM and garm-configurator are integrated; the configurator's ``org`` config
        ("test-org", set in the ``configurator_with_image`` fixture) drives a desired
        organization entity, but nothing has pre-registered it in GARM — unlike
        test_scaleset_created_and_updated_via_relation, which bypasses entity registration
        entirely by calling ``_create_test_org`` directly. This test exists to prove the charm's
        own EntityReconciler can register the entity end-to-end (regression test for the bug
        where GARM 500s org/repo creation without a non-empty webhook_secret).
    act: Set controller URLs (idempotent) and trigger a config change so GARM's holistic
        reconcile runs now that operational endpoints are unblocked.
    assert: GET /organizations lists "test-org" bound to the charm-managed credential
        (app-12345-67890) synced from the configurator relation.

    Cleanup: deletes the org via the GARM API afterwards. The later
        test_scaleset_created_and_updated_via_relation needs "test-org" bound to a *mock*-backed
        credential so scaleset creation can reach a controllable GitHub API double; leaving this
        test's charm-managed binding in place would make that test's ``_create_test_org`` call a
        no-op 409 and break it.
    """
    address = _get_garm_address(juju, configurator_garm)
    base_url = _garm_api_base_url(address)
    token = _garm_first_run(juju, address)  # idempotent; ensures controller URLs are set

    # A config change (distinct from the "10" used later) is the only way to make GARM re-run
    # _reconcile_runners now that the controller URLs are in place — nothing else re-triggers the
    # charm's holistic reconcile once first-run has set them via a direct API call.
    juju.config(configurator_with_image, values={"max-runner": "6"})
    juju.wait(
        lambda status: jubilant.all_active(status, configurator_with_image)
        and jubilant.all_agents_idle(status, configurator_garm),
        timeout=3 * 60,
        delay=10,
    )

    org = None
    try:
        org = _wait_for_org(base_url, token, "test-org")
        credential = _wait_for_github_credential(base_url, token, _SYNCED_CREDENTIAL_NAME)
        assert org["credentials_id"] == credential["id"], (
            f"Expected 'test-org' bound to charm-managed credential {_SYNCED_CREDENTIAL_NAME!r} "
            f"(id={credential['id']}), got credentials_id={org.get('credentials_id')!r}"
        )
    finally:
        if org is not None and org.get("id"):
            _delete_org(base_url, token, org["id"])


def test_scaleset_created_and_updated_via_relation(
    juju: jubilant.Juju,
    configurator_garm: str,
    configurator_with_image: str,
    fake_github_api_url: str,
):
    """
    arrange: GARM and garm-configurator are integrated and both active.
    act: Verify the scaleset is created and reflects updated config.
    assert: After a config change the scaleset exists with the new max_runners value.
    """
    address = _get_garm_address(juju, configurator_garm)
    base_url = _garm_api_base_url(address)

    # _garm_first_run sets the controller callback/metadata URLs that GARM requires
    # before it will serve operational endpoints (returns 409 otherwise).  The
    # configurator_garm fixture integrates the charms before these URLs exist, so
    # the first reconcile defers.  Calling _garm_first_run here is idempotent (PUT).
    token = _garm_first_run(juju, address)

    # Restore system templates so GARM can find a linux/github template when
    # CreateEntityScaleSet calls findTemplate internally.
    _restore_system_templates(base_url, token)

    # Create credential and org pointed at the mock GitHub API server so that
    # GARM's GitHub App calls (installation token, runner-groups, etc.) hit our
    # mock instead of real GitHub.
    _create_test_credential(base_url, token, fake_github_api_url)
    _create_test_org(base_url, token, "test-org")

    # A config change triggers config_changed on the configurator → relation_changed
    # on GARM → _reconcile_runners() runs now that URLs are configured.
    # Using max-runner=10 doubles as the update assertion below.
    juju.config(configurator_with_image, values={"max-runner": "10"})
    # Wait for GARM to settle. GARM is already active so this exits after one poll
    # (delay=10s), then _wait_for_scaleset polls while relation_changed fires.
    juju.wait(
        lambda status: jubilant.all_active(status, configurator_garm),
        timeout=3 * 60,
        delay=10,
    )

    scaleset = _wait_for_scaleset(base_url, token, _SCALESET_TEST_NAME)
    assert scaleset["name"] == _SCALESET_TEST_NAME
    assert scaleset["max_runners"] == 10


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


def garm_login_from_secret(juju: jubilant.Juju, garm_app_name: str, garm_url: str) -> str:
    """Log into the GARM API using admin credentials stored in Juju secrets."""
    secrets_json = juju.cli("secrets", "--format=json")
    all_secrets = json.loads(secrets_json)
    garm_secret_uri = next(
        (
            uri
            for uri, info in all_secrets.items()
            if info.get("label") == GARM_ADMIN_CREDENTIALS_LABEL
        ),
        None,
    )
    assert garm_secret_uri, f"{GARM_ADMIN_CREDENTIALS_LABEL} not found for {garm_app_name}"

    secret_json = juju.cli("show-secret", "--reveal", "--format=json", garm_secret_uri)
    secret_data = json.loads(secret_json)
    content = secret_data[garm_secret_uri]["content"]["Data"]
    admin_username = content["username"]
    admin_password = content["password"]

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


def _find_scaleset(scalesets: list[dict], name: str) -> dict | None:
    """Return the first scaleset with the requested name."""
    return next((scaleset for scaleset in scalesets if scaleset.get("name") == name), None)


_SCALESET_TEST_ENDPOINT_NAME = "mock-github-endpoint"


def _create_test_credential(garm_url: str, token: str, mock_base_url: str) -> str:
    """Create a GitHub App credential in GARM pointing at the mock server.

    Uses a dedicated endpoint name ``mock-github-endpoint`` (not the built-in
    ``github.com`` one) so that GARM routes all GitHub API calls to our mock
    instead of the real api.github.com.
    """

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
        # Create a dedicated endpoint pointing at the mock server.
        # GARM ships with a default "github.com" endpoint wired to
        # api.github.com; we use a different name so our credential is
        # guaranteed to use the mock URL for every GitHub API call.
        _request(
            "/github/endpoints",
            {
                "name": _SCALESET_TEST_ENDPOINT_NAME,
                "description": "Mock GitHub API endpoint for integration tests",
                "base_url": mock_base_url,
                "api_base_url": mock_base_url,
                "upload_base_url": mock_base_url,
            },
        )
        _request(
            "/github/credentials",
            {
                "name": _SCALESET_TEST_CREDENTIAL_NAME,
                "description": "Test credential for scaleset integration tests",
                "endpoint": _SCALESET_TEST_ENDPOINT_NAME,
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
                "base_url": mock_base_url,
                "api_base_url": mock_base_url,
                "upload_base_url": mock_base_url,
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



def _restore_system_templates(garm_url: str, token: str) -> None:
    """Restore GARM's built-in system templates so scaleset creation can find a template.

    GARM requires a matching template (os_type=linux, forge_type=github) to exist
    before CreateEntityScaleSet proceeds. This call restores all system templates.
    Silently succeeds if templates already exist.
    """
    data = json.dumps({"restore_all": True}).encode()
    req = urllib.request.Request(
        f"{garm_url}/templates/restore",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


def _create_test_org(garm_url: str, token: str, org_name: str) -> None:
    """Register a GitHub organization in GARM with the test credential.

    GARM requires an organization to be registered before a scaleset can be
    created for it.  Silently skips if the org already exists (409 Conflict).
    agent_mode=True prevents GARM from attempting to install a webhook using
    the fake credential, which would fail against the mock server.
    """
    data = json.dumps(
        {
            "name": org_name,
            "credentials_name": _SCALESET_TEST_CREDENTIAL_NAME,
            "webhook_secret": "test-webhook-secret",
            "agent_mode": True,
        }
    ).encode()
    req = urllib.request.Request(
        f"{garm_url}/organizations",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise



@retry(
    retry=retry_if_exception_type((AssertionError, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(30),
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


def _list_orgs(base_url: str, token: str) -> list[dict]:
    """List GARM organizations via the REST API (GARM returns null when empty)."""
    resp = requests.get(
        f"{base_url}/organizations", headers=_garm_auth_headers(token), timeout=30
    )
    resp.raise_for_status()
    return resp.json() or []


@retry(
    retry=retry_if_exception_type((AssertionError, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(30),
    reraise=True,
)
def _wait_for_org(base_url: str, token: str, name: str) -> dict:
    """Wait until a named organization is registered in GARM."""
    org = next((org for org in _list_orgs(base_url, token) if org.get("name") == name), None)
    assert org is not None, f"Expected organization {name!r} to exist"
    return org


def _delete_org(base_url: str, token: str, org_id: str) -> None:
    """Delete a GARM organization via the REST API."""
    resp = requests.delete(
        f"{base_url}/organizations/{org_id}", headers=_garm_auth_headers(token), timeout=30
    )
    resp.raise_for_status()


def _list_github_credentials(base_url: str, token: str) -> list[dict]:
    """List GARM GitHub credentials via the REST API (GARM returns null when empty)."""
    resp = requests.get(
        f"{base_url}/github/credentials", headers=_garm_auth_headers(token), timeout=30
    )
    resp.raise_for_status()
    return resp.json() or []


def _list_github_endpoints(base_url: str, token: str) -> list[dict]:
    """List GARM GitHub endpoints via the REST API (GARM returns null when empty)."""
    resp = requests.get(
        f"{base_url}/github/endpoints", headers=_garm_auth_headers(token), timeout=30
    )
    resp.raise_for_status()
    return resp.json() or []


@retry(
    retry=retry_if_exception_type((AssertionError, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(18),
    reraise=True,
)
def _wait_for_github_credential(base_url: str, token: str, name: str) -> dict:
    """Wait until a GitHub credential with the given name is synced into GARM."""
    credentials = _list_github_credentials(base_url, token)
    match = next((cred for cred in credentials if cred.get("name") == name), None)
    assert match is not None, (
        f"Expected credential {name!r} to exist; got {[c.get('name') for c in credentials]}"
    )
    return match


def test_github_credentials_synced_from_relation(
    juju: jubilant.Juju,
    configurator_garm: str,
):
    """
    arrange: GARM is integrated with a configurator that supplies GitHub App config
        (github-app-id, installation id, and a private-key Juju secret).
    act: Let the charm reconcile GitHub credentials from the relation data.
    assert: GARM holds an App credential derived from the relation data, and the
        built-in github.com endpoint is preserved (never deleted by the reconciler).
    """
    garm_app = configurator_garm
    address = _get_garm_address(juju, garm_app)
    base_url = _garm_api_base_url(address)
    token = _garm_first_run(juju, address)

    credential = _wait_for_github_credential(base_url, token, _SYNCED_CREDENTIAL_NAME)

    assert credential["name"] == _SYNCED_CREDENTIAL_NAME
    # GARM aliases the field as "auth-type"; tolerate either spelling across versions.
    auth_type = credential.get("auth-type") or credential.get("auth_type")
    assert auth_type == "app", f"Expected app auth, got {auth_type!r}"

    endpoint_names = {endpoint.get("name") for endpoint in _list_github_endpoints(base_url, token)}
    assert "github.com" in endpoint_names, (
        f"Built-in github.com endpoint must be preserved; got {sorted(endpoint_names)}"
    )

