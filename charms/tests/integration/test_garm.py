# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for the GARM charm."""

import base64
import json
import logging
import secrets
import urllib.request

import jubilant
import pytest
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tests.integration.conftest import (
    GARM_ADMIN_CREDENTIALS_LABEL,
    GARM_API_PORT,
    _garm_first_run,
    _get_garm_address,
)

logger = logging.getLogger(__name__)

GARM_BINARY = "/usr/local/bin/garm"
GARM_PROVIDER_BINARY = "/usr/local/bin/garm-provider-openstack"
GARM_CONFIG_PATH = "/etc/garm/config.toml"
GARM_SECRETS_LABEL = "garm-secrets"
PEBBLE_PREFIX = "PEBBLE_SOCKET=/charm/containers/app/pebble.socket /charm/bin/pebble"
GARM_CHARMED_TEMPLATE_NAME = "github_linux_charmed"

# Generated once per session so all test functions that call _garm_first_run use
# the same credentials. Format guarantees GARM's strong-password requirements:
# uppercase (A), lowercase (dmin + hex), digit (1 + hex), symbols (-, !).
_GARM_ADMIN_PASSWORD = f"Admin-{secrets.token_hex(8)}-X1!"
_SCALESET_TEST_NAME = "test-scaleset"
# Credential name the GARM charm derives from the configurator's github-app-id +
# installation id (12345 / 67890).
_SYNCED_CREDENTIAL_NAME = "app-12345-67890"
# GARM's built-in GitHub endpoint that the charm attaches all synced credentials to
# (mirrors DEFAULT_GITHUB_ENDPOINT in the charm's github_reconciler).
_GITHUB_COM_ENDPOINT = "github.com"


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
    assert: The application is up (``active``, or ``waiting`` on the GARM runner
        reconcile) rather than ``blocked`` or errored, confirming a successful install.

    The charm keeps the application status in sync with the unit status, so while
    _reconcile_runners() is still pending (GARM not yet fully initialised via the
    API) the application legitimately reports ``waiting`` instead of a stale
    ``active``.  Either state confirms the workload came up cleanly.
    """
    status = juju.status()
    app_status = status.apps[configurator_garm].app_status
    logger.info("GARM app status: %s (%s)", app_status.current, app_status.message)

    assert app_status.current in (
        "active",
        "waiting",
    ), f"Expected {configurator_garm} to be active or waiting, got: {app_status.current}"


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


def test_charm_reconciles_org_and_scaleset(
    juju: jubilant.Juju,
    configurator_garm: str,
    configurator_with_image: str,
    fake_github_api_url: str,
):
    """
    arrange: GARM and garm-configurator are integrated, driving a desired org ("test-org") and
        scaleset ("test-scaleset"); controller URLs are set and github.com is repointed at the
        mock so the charm's reconcile reaches a controllable GitHub double.
    act: Trigger a config change so the charm's holistic reconcile runs.
    assert: The charm registers "test-org" bound to the synced credential (app-12345-67890) and
        creates "test-scaleset" with the updated max_runners.
    """
    address = _get_garm_address(juju, configurator_garm)
    base_url = _garm_api_base_url(address)
    token = _garm_first_run(juju, address)  # idempotent; ensures controller URLs are set

    # GARM refuses to change an endpoint's URLs while a credential references it, and the charm has
    # already synced its credential onto github.com during integration. Detach the charm-managed
    # org (if any) and credential so github.com can be repointed; the reconcile triggered below
    # recreates both against the mock.
    _detach_synced_credential(base_url, token)
    # Route the charm's synced credential (bound to github.com) at the mock so the whole
    # reconcile — credential sync, org registration, scaleset creation — hits a controllable
    # GitHub double. GARM permits updating (not deleting) its built-in endpoint.
    _point_github_endpoint_at_mock(base_url, token, fake_github_api_url)
    # Restore system templates so GARM can find a linux/github template when
    # CreateEntityScaleSet calls findTemplate internally.
    _restore_system_templates(base_url, token)

    # A config change triggers config_changed on the configurator → relation_changed on GARM →
    # _reconcile_runners() runs now that the controller URLs are set. max-runner=10 doubles as the
    # scaleset assertion below.
    juju.config(configurator_with_image, values={"max-runner": "10"})
    juju.wait(
        lambda status: jubilant.all_active(status, configurator_with_image)
        and jubilant.all_agents_idle(status, configurator_garm),
        timeout=3 * 60,
        delay=10,
    )

    org = _wait_for_org(base_url, token, "test-org")
    credential = _wait_for_github_credential(base_url, token, _SYNCED_CREDENTIAL_NAME)
    assert org["credentials_id"] == credential["id"], (
        f"Expected 'test-org' bound to charm-managed credential {_SYNCED_CREDENTIAL_NAME!r} "
        f"(id={credential['id']}), got credentials_id={org.get('credentials_id')!r}"
    )

    scaleset = _wait_for_scaleset(base_url, token, _SCALESET_TEST_NAME)
    assert scaleset["name"] == _SCALESET_TEST_NAME
    assert scaleset["max_runners"] == 10

    templates = _list_templates(address, token)
    charmed = next((t for t in templates if t.get("name") == GARM_CHARMED_TEMPLATE_NAME), None)
    assert charmed is not None, "charmed template should always be maintained by reconcile"
    assert scaleset.get("template_id") == charmed["id"], (
        f"scaleset should reference charmed template id {charmed['id']}; "
        f"got {scaleset.get('template_id')}"
    )


def _list_templates(address: str, token: str) -> list[dict]:
    """List all runner install templates from the GARM API.

    Args:
        address: GARM unit IP address.
        token: JWT token for authentication.

    Returns:
        List of template dicts from the GARM API.
    """
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/templates", headers=headers, timeout=30)
    resp.raise_for_status()
    templates = resp.json()
    return templates if isinstance(templates, list) else []


def _get_template_body(address: str, token: str, template_id: int) -> str:
    """Fetch a template by ID and return its decoded script body.

    The GARM list API omits the ``data`` field for performance; this helper
    fetches the individual template and base64-decodes the script bytes.

    Args:
        address: GARM unit IP address.
        token: JWT token for authentication.
        template_id: Numeric template ID to fetch.

    Returns:
        Decoded UTF-8 script string, or empty string if ``data`` is absent.
    """
    base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{base_url}/templates/{template_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    raw_b64 = resp.json().get("data") or ""
    return base64.b64decode(raw_b64).decode("utf-8") if raw_b64 else ""


def test_garm_charmed_template_created_on_debug_ssh(
    juju: jubilant.Juju,
    garm_with_debug_ssh: str,
):
    """
    arrange: The debug-ssh relation is integrated with a fake tmate server; the
        github_linux base template was pre-created in GARM.
    act: Query GET /api/v1/templates with an admin JWT.
    assert: The github_linux_charmed template exists and its body contains
        the tmate env-var snippet for the fake server's host and port.
    """
    address = _get_garm_address(juju, garm_with_debug_ssh)
    token = _garm_first_run(juju, address)

    templates = _list_templates(address, token)
    logger.info(
        "Templates after debug-ssh integration: %s",
        [t.get("name") for t in templates],
    )

    charmed = next((t for t in templates if t.get("name") == GARM_CHARMED_TEMPLATE_NAME), None)
    assert charmed is not None, (
        f"Expected '{GARM_CHARMED_TEMPLATE_NAME}' template to exist after debug-ssh "
        f"integration; found templates: {[t.get('name') for t in templates]}"
    )

    body = _get_template_body(address, token, charmed["id"])
    logger.info("Charmed template body (first 500 chars):\n%s", body[:500])

    assert "TMATE_SERVER_HOST=tmate.example.com" in body, (
        f"Expected TMATE_SERVER_HOST in charmed template body; got:\n{body[:500]}"
    )
    assert "TMATE_SERVER_PORT=2200" in body, (
        f"Expected TMATE_SERVER_PORT in charmed template body; got:\n{body[:500]}"
    )


def test_garm_charmed_template_persists_without_tmate_on_debug_ssh_removal(
    juju: jubilant.Juju,
    garm_without_debug_ssh: str,
):
    """
    arrange: The debug-ssh relation has been removed from GARM.
    act: Query GET /api/v1/templates with an admin JWT.
    assert: The github_linux_charmed template still exists (scalesets always
        reference it) but its body no longer contains the tmate env-var snippet.
    """
    address = _get_garm_address(juju, garm_without_debug_ssh)
    token = _garm_first_run(juju, address)

    templates = _list_templates(address, token)
    template_names = [t.get("name") for t in templates]
    logger.info("Templates after debug-ssh removal: %s", template_names)

    charmed = next((t for t in templates if t.get("name") == GARM_CHARMED_TEMPLATE_NAME), None)
    assert charmed is not None, (
        f"Expected '{GARM_CHARMED_TEMPLATE_NAME}' to persist after debug-ssh "
        f"relation removal; found templates: {template_names}"
    )

    body = _get_template_body(address, token, charmed["id"])
    assert "TMATE_SERVER_HOST" not in body, (
        f"Expected tmate snippet removed from charmed template after debug-ssh "
        f"removal; got:\n{body[:500]}"
    )


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


def _point_github_endpoint_at_mock(base_url: str, token: str, mock_base_url: str) -> None:
    """Repoint GARM's built-in github.com endpoint at the mock GitHub API.

    The charm attaches every synced credential to GARM's built-in ``github.com`` endpoint
    (its DEFAULT_GITHUB_ENDPOINT, not configurable). Overwriting that endpoint's base URLs is
    the only lever that makes the charm's own GitHub App calls — installation token, runner
    groups, scaleset creation — resolve to a controllable double instead of api.github.com,
    letting a single test exercise the full charm reconcile. GARM allows updating (but not
    deleting) the built-in endpoint.
    """
    resp = requests.put(
        f"{base_url}/github/endpoints/{_GITHUB_COM_ENDPOINT}",
        json={
            "base_url": mock_base_url,
            "api_base_url": mock_base_url,
            "upload_base_url": mock_base_url,
        },
        headers=_garm_auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()


def _detach_synced_credential(base_url: str, token: str) -> None:
    """Delete the charm-synced scalesets, org and credential so github.com can be repointed."""
    # GARM locks an endpoint's URLs while a credential references it, refuses to delete a
    # credential while an org is bound to it, and refuses to delete an org while a scaleset
    # references it. The charm syncs its credential onto the built-in github.com endpoint, so the
    # chain must be unwound in dependency order — scalesets, then org, then credential — before
    # the endpoint can be repointed at the mock.
    _delete_scalesets(base_url, token)
    for org in _list_orgs(base_url, token):
        if org.get("name") == "test-org" and org.get("id"):
            _delete_if_present(f"{base_url}/organizations/{org['id']}", token)
    for cred in _list_github_credentials(base_url, token):
        if cred.get("name") == _SYNCED_CREDENTIAL_NAME and cred.get("id") is not None:
            _delete_if_present(f"{base_url}/github/credentials/{cred['id']}", token)


def _delete_if_present(url: str, token: str) -> None:
    """DELETE a GARM resource, treating 404 as already-gone."""
    resp = requests.delete(url, headers=_garm_auth_headers(token), timeout=30)
    if resp.status_code == requests.codes.not_found:
        return
    if not resp.ok:
        logger.warning("DELETE %s -> %s: %s", url, resp.status_code, resp.text)
    resp.raise_for_status()


def _delete_scalesets(base_url: str, token: str) -> None:
    """Disable and delete every scaleset."""
    for scaleset in _list_scalesets(base_url, token):
        scaleset_id = scaleset.get("id")
        if scaleset_id is None:
            continue
        # GARM 400s a scaleset delete while the scaleset is still enabled or draining runners, so
        # disable it (idle count to zero) to trigger the drain before deleting.
        resp = requests.put(
            f"{base_url}/scalesets/{scaleset_id}",
            json={"enabled": False, "min_idle_runners": 0},
            headers=_garm_auth_headers(token),
            timeout=30,
        )
        resp.raise_for_status()
        _delete_scaleset_drained(base_url, token, scaleset_id)


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    stop=stop_after_attempt(20),
    reraise=True,
)
def _delete_scaleset_drained(base_url: str, token: str, scaleset_id: int) -> None:
    """DELETE a scaleset, retrying while GARM drains it (400); 404 means already gone."""
    _delete_if_present(f"{base_url}/scalesets/{scaleset_id}", token)


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


def _get_template_data(base_url: str, token: str, template_id: int) -> str:
    """Fetch a GARM template and return its decoded (base64) script content.

    Args:
        base_url: GARM API base URL.
        token: JWT token for authentication.
        template_id: Integer template ID.

    Returns:
        The decoded template script as a string.
    """
    resp = requests.get(
        f"{base_url}/templates/{template_id}",
        headers=_garm_auth_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("data", "")
    return base64.b64decode(data).decode() if data else ""


@retry(
    retry=retry_if_exception_type((AssertionError, requests.exceptions.RequestException)),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(30),
    reraise=True,
)
def _wait_for_scaleset_template_data(
    base_url: str,
    token: str,
    scaleset_name: str,
    expected_markers: tuple[str, ...],
) -> str:
    """Wait until a scaleset references a template containing the expected markers."""
    scaleset = _wait_for_scaleset(base_url, token, scaleset_name)
    template_id = scaleset.get("template_id")
    assert template_id, f"Expected scaleset to reference a custom template, got: {scaleset}"

    rendered = _get_template_data(base_url, token, template_id)
    missing = [marker for marker in expected_markers if marker not in rendered]
    assert not missing, (
        f"Expected markers {missing!r} in rendered template {template_id}, got:\n{rendered}"
    )
    return rendered


def test_runner_options_render_into_scaleset_template(
    juju: jubilant.Juju,
    configurator_garm: str,
    configurator_with_image: str,
    fake_github_api_url: str,
):
    """
    arrange: GARM and garm-configurator are integrated, with a credential and org
        registered so a scaleset can be created.
    act: Set the runner-behaviour config options on the configurator charm.
    assert: The scaleset references a custom template whose rendered content
        reflects each runner option — proving the options reach GARM via live
        reconcile (no upgrade).
    """
    address = _get_garm_address(juju, configurator_garm)
    base_url = _garm_api_base_url(address)
    token = _garm_first_run(juju, address)
    _detach_synced_credential(base_url, token)
    _point_github_endpoint_at_mock(base_url, token, fake_github_api_url)
    _restore_system_templates(base_url, token)

    juju.config(
        configurator_with_image,
        values={
            "dockerhub-mirror": "https://mirror.example.com",
            "runner-http-proxy": "http://proxy.example.com:3128",
            "aproxy-exclude-addresses": "192.168.0.0/16",
            "aproxy-redirect-ports": "80,443",
            "otel-collector-endpoint": "http://otel.example.com:4318",
            "pre-job-script": "echo integration-marker",
        },
    )
    juju.wait(
        lambda status: jubilant.all_active(status, configurator_with_image)
        and jubilant.all_agents_idle(status, configurator_garm),
        timeout=3 * 60,
        delay=10,
    )

    # One marker per config option, proving each reaches GARM via live reconcile:
    # dockerhub-mirror (daemon.json + env var), runner-http-proxy + aproxy-*
    # (aproxy listener and nftables ruleset), otel-collector-endpoint (env var),
    # and pre-job-script (job-start hook).
    expected_markers = (
        "registry-mirrors",
        "DOCKERHUB_MIRROR=https://mirror.example.com",
        "proxy=http://proxy.example.com:3128 listen=:54969",
        "192.168.0.0/16",
        "tcp dport { 80, 443 }",
        "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel.example.com:4318",
        "echo integration-marker",
    )
    # Asserts each expected marker is present in the referenced template, retrying
    # until GARM reflects the reconciled config.
    _wait_for_scaleset_template_data(
        base_url,
        token,
        _SCALESET_TEST_NAME,
        expected_markers,
    )
