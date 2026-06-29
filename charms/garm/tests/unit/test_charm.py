# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import string
from unittest.mock import MagicMock, PropertyMock, patch

import ops
import pytest
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import (
    GARM_ADMIN_CREDENTIALS_LABEL,
    GARM_PORT,
    GARM_SECRETS_LABEL,
    GarmCharm,
    _build_provider_list,
    _generate_admin_password,
    _generate_garm_secrets,
    render_garm_toml,
)
from garm_api import GarmConnectionError
from github_reconciler import DEFAULT_GITHUB_ENDPOINT

_DEFAULT_PG_CONFIG = {
    "username": "u",
    "password": "p",
    "hostname": "h",
    "port": 5432,
    "database": "d",
    "sslmode": "disable",
}


def _render(**overrides) -> dict:
    """Helper: render TOML with defaults, return parsed dict."""
    kwargs = {
        "jwt_secret": "test-secret",
        "db_passphrase": "a" * 32,
        "postgresql_config": _DEFAULT_PG_CONFIG,
    }
    kwargs.update(overrides)
    toml_content, _ = render_garm_toml(**kwargs)
    return tomllib.loads(toml_content)


def test_render_garm_toml_postgresql_backend():
    """The [database] section uses postgresql backend with correct fields."""
    parsed = _render(
        postgresql_config={
            "username": "garm",
            "password": "secret",
            "hostname": "10.0.0.5",
            "port": 5432,
            "database": "garm_db",
            "sslmode": "require",
        },
    )
    assert parsed["database"]["backend"] == "postgresql"
    assert parsed["database"]["postgresql"]["hostname"] == "10.0.0.5"
    assert parsed["database"]["postgresql"]["username"] == "garm"
    assert parsed["database"]["postgresql"]["password"] == "secret"
    assert parsed["database"]["postgresql"]["port"] == 5432
    assert parsed["database"]["postgresql"]["database"] == "garm_db"
    assert parsed["database"]["postgresql"]["sslmode"] == "require"
    assert "sqlite3" not in parsed["database"]


def test_render_garm_toml_passphrase_in_database_section():
    """The passphrase appears in the [database] section."""
    passphrase = "b" * 32
    parsed = _render(db_passphrase=passphrase)
    assert parsed["database"]["passphrase"] == passphrase


@pytest.mark.parametrize(
    "sslmode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
)
def test_render_garm_toml_sslmode_propagated(sslmode: str):
    """The sslmode value is propagated to the postgresql section."""
    pg_config = {**_DEFAULT_PG_CONFIG, "sslmode": sslmode}
    parsed = _render(postgresql_config=pg_config)
    assert parsed["database"]["postgresql"]["sslmode"] == sslmode


@pytest.mark.parametrize(
    "section,key,value,kwargs",
    [
        ("apiserver", "bind", "0.0.0.0", {}),
        ("apiserver", "port", 8080, {}),
        ("apiserver", "use_tls", False, {}),
        ("jwt_auth", "secret", "mysecret", {"jwt_secret": "mysecret"}),
        ("jwt_auth", "time_to_live", "8760h", {}),
        ("metrics", "disable_auth", True, {}),
        ("metrics", "enable", True, {}),
    ],
    ids=[
        "apiserver-bind",
        "apiserver-port",
        "apiserver-use_tls",
        "jwt_auth-secret",
        "jwt_auth-time_to_live",
        "metrics-disable_auth",
        "metrics-enable",
    ],
)
def test_render_garm_toml_section_fields(section: str, key: str, value, kwargs: dict):
    """Config sections reflect the given parameters."""
    parsed = _render(**kwargs)
    assert parsed[section][key] == value


def test_render_garm_toml_provider_section():
    """The [[provider]] section has the OpenStack provider binary."""
    parsed = _render()
    assert len(parsed["provider"]) == 1
    provider = parsed["provider"][0]
    assert provider["name"] == "openstack"
    assert provider["provider_type"] == "external"
    assert provider["external"]["provider_executable"] == "/usr/local/bin/garm-provider-openstack"


def test_generate_garm_secrets_returns_jwt_and_passphrase():
    """Returns a dict with jwt-secret (64-char hex) and db-passphrase (32-char alnum)."""
    result = _generate_garm_secrets()
    assert "jwt-secret" in result
    assert "db-passphrase" in result
    assert len(result["jwt-secret"]) == 64
    assert all(c in "0123456789abcdef" for c in result["jwt-secret"])
    assert len(result["db-passphrase"]) == 32
    valid_chars = string.ascii_letters + string.digits
    assert all(c in valid_chars for c in result["db-passphrase"])


def test_generate_garm_secrets_produces_unique_values():
    """Two calls return different secrets."""
    first = _generate_garm_secrets()
    second = _generate_garm_secrets()
    assert first["jwt-secret"] != second["jwt-secret"]
    assert first["db-passphrase"] != second["db-passphrase"]


def test_render_garm_toml_with_configurator_providers():
    """
    arrange: Two Configurator units provided provider configs.
    act: render_garm_toml is called with providers list.
    assert: Two [[provider]] blocks are rendered with correct names and
            config_file paths pointing to provider TOML files.  The
            returned provider_files dict contains the provider TOML and
            clouds.yaml for each provider.
    """
    providers = [
        {
            "unit_name": "garm-configurator-0",
            "auth_url": "https://ks1.example.com:5000/v3",
            "username": "admin1",
            "password": "pass1",
            "project_name": "proj1",
            "user_domain_name": "Default",
            "project_domain_name": "Default",
            "region_name": "RegionOne",
            "network": "net1",
        },
        {
            "unit_name": "garm-configurator-1",
            "auth_url": "https://ks2.example.com:5000/v3",
            "username": "admin2",
            "password": "pass2",
            "project_name": "proj2",
            "user_domain_name": "Default",
            "project_domain_name": "Default",
            "region_name": "RegionTwo",
            "network": "net2",
        },
    ]
    toml_content, provider_files = render_garm_toml(
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=providers,
    )
    parsed = tomllib.loads(toml_content)
    assert len(parsed["provider"]) == 2

    p0 = parsed["provider"][0]
    assert p0["name"] == "garm-configurator-0"
    assert p0["external"]["provider_executable"] == "/usr/local/bin/garm-provider-openstack"
    assert p0["external"]["config_file"] == "/etc/garm/provider-garm-configurator-0.toml"
    assert "environment_variables" not in p0["external"]

    p1 = parsed["provider"][1]
    assert p1["name"] == "garm-configurator-1"
    assert p1["external"]["config_file"] == "/etc/garm/provider-garm-configurator-1.toml"

    # Verify provider_files contains the expected paths and content.
    provider_toml_0 = provider_files["/etc/garm/provider-garm-configurator-0.toml"]
    assert 'network_id = "net1"' in provider_toml_0
    assert 'cloud = "garm-configurator-0"' in provider_toml_0

    clouds_yaml_0 = provider_files["/etc/garm/clouds-garm-configurator-0.yaml"]
    clouds_0 = yaml.safe_load(clouds_yaml_0)
    assert clouds_0["clouds"]["garm-configurator-0"]["auth"]["username"] == "admin1"
    assert clouds_0["clouds"]["garm-configurator-0"]["auth"]["password"] == "pass1"
    assert clouds_0["clouds"]["garm-configurator-0"]["region_name"] == "RegionOne"

    clouds_yaml_1 = provider_files["/etc/garm/clouds-garm-configurator-1.yaml"]
    clouds_1 = yaml.safe_load(clouds_yaml_1)
    assert clouds_1["clouds"]["garm-configurator-1"]["auth"]["username"] == "admin2"
    assert clouds_1["clouds"]["garm-configurator-1"]["auth"]["password"] == "pass2"


def test_build_provider_list_returns_default_when_empty():
    """
    arrange: An empty list is passed.
    act: _build_provider_list is called.
    assert: Returns the default single-entry list with "openstack" provider.
    """
    entries, files = _build_provider_list([])
    assert len(entries) == 1
    assert entries[0]["name"] == "openstack"
    assert files == {}


def test_build_provider_list_password_in_clouds_yaml():
    """
    arrange: Two provider configs with passwords.
    act: _build_provider_list is called.
    assert: Both providers have their password rendered in clouds.yaml.
            The password is resolved from Juju secrets in
            _get_configurator_provider_configs before reaching
            _build_provider_list, so it's always available as plaintext.
    """
    providers = [
        {
            "unit_name": "garm-configurator-0",
            "auth_url": "https://ks1.example.com:5000/v3",
            "username": "admin1",
            "password": "pass1",
            "project_name": "proj1",
            "user_domain_name": "Default",
            "project_domain_name": "Default",
            "region_name": "RegionOne",
            "network": "net1",
        },
        {
            "unit_name": "garm-configurator-1",
            "auth_url": "https://ks2.example.com:5000/v3",
            "username": "admin2",
            "password": "pass2",
            "project_name": "proj2",
            "user_domain_name": "Default",
            "project_domain_name": "Default",
            "region_name": "RegionTwo",
            "network": "net2",
        },
    ]
    entries, provider_files = _build_provider_list(providers)
    assert len(entries) == 2

    clouds_yaml_0 = provider_files["/etc/garm/clouds-garm-configurator-0.yaml"]
    clouds_0 = yaml.safe_load(clouds_yaml_0)
    assert clouds_0["clouds"]["garm-configurator-0"]["auth"]["password"] == "pass1"
    assert clouds_0["clouds"]["garm-configurator-0"]["auth"]["username"] == "admin1"
    assert clouds_0["clouds"]["garm-configurator-0"]["region_name"] == "RegionOne"

    clouds_yaml_1 = provider_files["/etc/garm/clouds-garm-configurator-1.yaml"]
    clouds_1 = yaml.safe_load(clouds_yaml_1)
    assert clouds_1["clouds"]["garm-configurator-1"]["auth"]["password"] == "pass2"

    assert entries[0]["external"]["config_file"] == "/etc/garm/provider-garm-configurator-0.toml"
    assert entries[1]["external"]["config_file"] == "/etc/garm/provider-garm-configurator-1.toml"


def test_render_clouds_yaml_quotes_special_chars():
    """
    arrange: A password containing YAML-significant characters (colon, hash).
    act: _render_clouds_yaml is called (via _build_provider_list).
    assert: The resulting clouds.yaml is valid YAML and the password
            parses correctly (not truncated or misinterpreted).
    """
    providers = [
        {
            "unit_name": "special-provider",
            "auth_url": "https://keystone.example.com:5000/v3",
            "username": "admin",
            "password": "p@ss:w0rd#123",
            "project_name": "proj",
            "user_domain_name": "Default",
            "project_domain_name": "Default",
            "region_name": "RegionOne",
            "network": "net1",
        },
    ]
    _, provider_files = _build_provider_list(providers)
    clouds_yaml = provider_files["/etc/garm/clouds-special-provider.yaml"]
    parsed = yaml.safe_load(clouds_yaml)
    assert parsed["clouds"]["special-provider"]["auth"]["password"] == "p@ss:w0rd#123"


def test_generate_admin_password_meets_garm_policy():
    """
    arrange: No setup required.
    act: Call _generate_admin_password().
    assert: The result satisfies GARM's strong-password requirements.
    """
    password = _generate_admin_password()
    assert len(password) >= 12
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)
    assert any(c.isdigit() for c in password)
    symbols = set(password) - set(string.ascii_letters + string.digits)
    assert len(symbols) > 0


def test_generate_admin_password_produces_unique_values():
    """
    arrange: No setup required.
    act: Call _generate_admin_password() twice.
    assert: The two passwords are different.
    """
    assert _generate_admin_password() != _generate_admin_password()


_MOCK_ADMIN_CREDS = {
    "username": "admin",
    "password": "TestPass-123!",
    "email": "admin@garm.local",
    "full-name": "GARM Admin",
}


def test_get_admin_credentials_returns_content_when_secret_exists():
    """
    arrange: garm-admin-credentials secret exists in Juju.
    act: Call _get_admin_credentials().
    assert: Returns the secret content dict.
    """
    charm = MagicMock()
    mock_secret = MagicMock()
    mock_secret.get_content.return_value = _MOCK_ADMIN_CREDS
    charm.model.get_secret.return_value = mock_secret

    result = GarmCharm._get_admin_credentials(charm)

    assert result == _MOCK_ADMIN_CREDS


def test_get_admin_credentials_returns_none_when_secret_not_found():
    """
    arrange: garm-admin-credentials secret does not exist in Juju.
    act: Call _get_admin_credentials().
    assert: Returns None.
    """
    charm = MagicMock()
    charm.model.get_secret.side_effect = ops.SecretNotFoundError("not found")

    result = GarmCharm._get_admin_credentials(charm)

    assert result is None


def test_ensure_secrets_skips_when_not_leader():
    """
    arrange: Unit is not the Juju leader.
    act: Call _ensure_secrets().
    assert: No secrets are created.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = False

    GarmCharm._ensure_secrets(charm)

    charm.app.add_secret.assert_not_called()


def test_ensure_secrets_creates_both_secrets_on_first_run():
    """
    arrange: Leader unit; neither garm-secrets nor garm-admin-credentials exist.
    act: Call _ensure_secrets().
    assert: Both secrets are created, labelled correctly.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True
    charm.model.get_secret.side_effect = ops.SecretNotFoundError("not found")

    GarmCharm._ensure_secrets(charm)

    assert charm.app.add_secret.call_count == 2
    labels = {c.kwargs["label"] for c in charm.app.add_secret.call_args_list}
    assert GARM_SECRETS_LABEL in labels
    assert GARM_ADMIN_CREDENTIALS_LABEL in labels


def test_ensure_secrets_skips_creation_when_secrets_exist():
    """
    arrange: Leader unit; both secrets already exist in Juju.
    act: Call _ensure_secrets().
    assert: No secrets are created.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True

    GarmCharm._ensure_secrets(charm)

    charm.app.add_secret.assert_not_called()


def test_maybe_first_run_skips_when_not_leader():
    """
    arrange: Unit is not the Juju leader.
    act: Call _maybe_first_run().
    assert: No GARM API call is made.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = False

    with patch("charm.GarmApiClient") as mock_client_cls:
        GarmCharm._maybe_first_run(charm)

    mock_client_cls.assert_not_called()


def test_maybe_first_run_skips_when_credentials_unavailable():
    """
    arrange: Leader unit; admin credentials secret does not exist yet.
    act: Call _maybe_first_run().
    assert: No GARM API call is made.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True
    charm._get_admin_credentials.return_value = None

    with patch("charm.GarmApiClient") as mock_client_cls:
        GarmCharm._maybe_first_run(charm)

    mock_client_cls.assert_not_called()


def test_maybe_first_run_skips_when_already_initialized():
    """
    arrange: Leader unit with valid credentials; GarmApiClient.is_initialized returns True.
    act: Call _maybe_first_run().
    assert: first_run is not called on the client.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True
    charm._get_admin_credentials.return_value = _MOCK_ADMIN_CREDS

    with patch("charm.GarmApiClient") as mock_client_cls:
        mock_client_cls.return_value.is_initialized.return_value = True
        GarmCharm._maybe_first_run(charm)

    mock_client_cls.return_value.first_run.assert_not_called()


def test_maybe_first_run_calls_first_run_when_not_initialized():
    """
    arrange: Leader unit with valid credentials; GarmApiClient.is_initialized returns False.
    act: Call _maybe_first_run().
    assert: first_run is called with the admin credentials.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True
    charm._get_admin_credentials.return_value = _MOCK_ADMIN_CREDS

    with patch("charm.GarmApiClient") as mock_client_cls:
        mock_client_cls.return_value.is_initialized.return_value = False
        GarmCharm._maybe_first_run(charm)

    mock_client_cls.return_value.first_run.assert_called_once_with(
        username="admin",
        password="TestPass-123!",
        email="admin@garm.local",
        full_name="GARM Admin",
    )


@pytest.mark.parametrize(
    "error_message",
    ["refused", "GARM did not become ready within 30s"],
    ids=["connection-refused", "timeout"],
)
def test_maybe_first_run_raises_on_connection_error(error_message: str):
    """
    arrange: Leader unit; GarmApiClient.wait_for_ready raises GarmConnectionError.
    act: Call _maybe_first_run().
    assert: GarmConnectionError propagates and is_initialized is not called.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True
    charm._get_admin_credentials.return_value = _MOCK_ADMIN_CREDS

    with patch("charm.GarmApiClient") as mock_client_cls:
        mock_client_cls.return_value.wait_for_ready.side_effect = GarmConnectionError(
            error_message
        )
        with pytest.raises(GarmConnectionError):
            GarmCharm._maybe_first_run(charm)
        mock_client_cls.return_value.is_initialized.assert_not_called()


def test_maybe_first_run_skips_on_missing_credential_key():
    """
    arrange: Leader unit; admin credentials secret is missing required keys.
    act: Call _maybe_first_run().
    assert: No GARM API call is made.
    """
    charm = MagicMock()
    charm.unit.is_leader.return_value = True
    charm._get_admin_credentials.return_value = {"username": "admin"}  # missing password etc.

    with patch("charm.GarmApiClient") as mock_client_cls:
        GarmCharm._maybe_first_run(charm)

    mock_client_cls.assert_not_called()


def test_reconcile_runners_skips_when_no_admin_credentials():
    """
    arrange: Admin credentials secret is unavailable.
    act: Call _reconcile_runners().
    assert: No GARM API connection is attempted.
    """
    charm = object.__new__(GarmCharm)
    charm._get_admin_credentials = MagicMock(return_value=None)

    with patch("charm.GarmAuthenticatedClient") as mock_auth_cls:
        charm._reconcile_runners()

    mock_auth_cls.from_login.assert_not_called()


def test_reconcile_runners_reconciles_github_then_scalesets():
    """
    arrange: Admin credentials are available and the desired credential/scaleset specs are stubbed.
    act: Call _reconcile_runners().
    assert: On a single authenticated client it configures controller URLs, reconciles GitHub
        credentials, then reconciles scalesets, reports ActiveStatus, and never restarts.
    """
    charm = object.__new__(GarmCharm)
    charm._get_admin_credentials = MagicMock(
        return_value={"username": "admin", "password": "TestPass-123!"}
    )
    credentials = [object()]
    scalesets = [object()]
    charm._build_desired_credentials = MagicMock(return_value=credentials)
    charm._build_desired_scalesets = MagicMock(return_value=scalesets)
    charm._ensure_controller_urls = MagicMock()
    charm.restart = MagicMock()

    with (
        patch("charm.GarmAuthenticatedClient") as mock_auth_cls,
        patch("charm.GithubReconciler") as mock_github_cls,
        patch("charm.ScalesetReconciler") as mock_scaleset_cls,
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
    ):
        mock_unit.return_value = MagicMock()
        charm._reconcile_runners()

    expected_url = f"http://127.0.0.1:{GARM_PORT}/api/v1"
    mock_auth_cls.from_login.assert_called_once_with(expected_url, "admin", "TestPass-123!")
    auth_client = mock_auth_cls.from_login.return_value
    # Controller URLs must be configured before any operational call, or GARM returns 409.
    charm._ensure_controller_urls.assert_called_once_with(auth_client)
    mock_github_cls.assert_called_once_with(auth_client)
    mock_github_cls.return_value.reconcile.assert_called_once_with(credentials)
    mock_scaleset_cls.assert_called_once_with(auth_client)
    mock_scaleset_cls.return_value.reconcile.assert_called_once_with(scalesets)
    charm.restart.assert_not_called()


def test_restart_ensures_secrets_before_readiness_gate():
    """
    arrange: A GarmCharm whose workload is not ready (pebble not up yet).
    act: Call restart().
    assert: _ensure_secrets is invoked even though is_ready() returns False,
            so secrets are created before pebble is up (install/leader_elected).
    """
    charm = object.__new__(GarmCharm)
    charm._ensure_secrets = MagicMock()
    charm.is_ready = MagicMock(return_value=False)

    charm.restart()

    charm._ensure_secrets.assert_called_once()


def test_reconcile_calls_restart():
    """
    arrange: A bare GarmCharm instance with restart and _create_charm_state mocked
             (the latter so the block_if_invalid_data decorator does not raise).
    act: Call _reconcile.
    assert: restart is called — every observed hook flows through _reconcile.
    """
    charm = object.__new__(GarmCharm)
    charm.restart = MagicMock()
    charm._create_charm_state = MagicMock()

    GarmCharm._reconcile(charm, MagicMock())

    charm.restart.assert_called_once()


def _github_charm(units_data, private_key="-----PEM-----"):
    """Build a GarmCharm stub whose configurator relation exposes the given unit databags."""
    charm = MagicMock(spec=GarmCharm)
    relation = MagicMock()
    data_map = {}
    for unit_data in units_data:
        unit = MagicMock()
        data_map[unit] = unit_data
    relation.units = list(data_map)
    relation.data = data_map
    charm.model.relations.get.return_value = [relation]
    charm._resolve_secret_value.return_value = private_key
    return charm


def test_build_desired_credentials_builds_credential_from_relation():
    """
    arrange: A charm whose configurator relation exposes one unit with app id, installation id
        and a private-key secret URI.
    act: Call _build_desired_credentials.
    assert: One App credential is built (named app-<app_id>-<installation_id>) on the built-in
        github.com endpoint, with the private key resolved from the secret.
    """
    charm = _github_charm(
        [
            {
                "github_app_id": "12345",
                "github_installation_id": "67890",
                "github_private_key_secret_uri": "secret:abc",
            }
        ],
        private_key="PEMDATA",
    )

    credentials = GarmCharm._build_desired_credentials(charm)

    assert len(credentials) == 1
    cred = credentials[0]
    assert cred.name == "app-12345-67890"
    assert cred.endpoint == DEFAULT_GITHUB_ENDPOINT
    assert cred.app_id == 12345
    assert cred.installation_id == 67890
    assert cred.private_key_bytes == list(b"PEMDATA")
    charm._resolve_secret_value.assert_called_once_with("secret:abc")


def test_build_desired_credentials_dedupes_per_app_installation():
    """
    arrange: A charm whose configurator relation exposes two units sharing one App/installation.
    act: Call _build_desired_credentials.
    assert: The two units collapse to a single credential.
    """
    unit_data = {
        "github_app_id": "1",
        "github_installation_id": "2",
        "github_private_key_secret_uri": "secret:k",
    }
    charm = _github_charm([dict(unit_data), dict(unit_data)])

    credentials = GarmCharm._build_desired_credentials(charm)

    assert len(credentials) == 1


def test_build_desired_credentials_skips_incomplete_unit():
    """
    arrange: A charm whose configurator relation exposes a unit missing required GitHub fields.
    act: Call _build_desired_credentials.
    assert: No credential is built.
    """
    charm = _github_charm([{"github_app_id": "1"}])

    credentials = GarmCharm._build_desired_credentials(charm)

    assert credentials == []


def test_build_desired_credentials_skips_when_secret_unavailable():
    """
    arrange: A charm whose configurator unit is complete but whose private-key secret resolves
        to an empty string.
    act: Call _build_desired_credentials.
    assert: No credential is built.
    """
    charm = _github_charm(
        [
            {
                "github_app_id": "1",
                "github_installation_id": "2",
                "github_private_key_secret_uri": "secret:k",
            }
        ],
        private_key="",
    )

    credentials = GarmCharm._build_desired_credentials(charm)

    assert credentials == []


def test_build_desired_credentials_skips_non_numeric_ids():
    """
    arrange: A charm whose configurator unit has a non-numeric app/installation id.
    act: Call _build_desired_credentials.
    assert: No credential is built.
    """
    charm = _github_charm(
        [
            {
                "github_app_id": "not-a-number",
                "github_installation_id": "2",
                "github_private_key_secret_uri": "secret:k",
            }
        ]
    )

    credentials = GarmCharm._build_desired_credentials(charm)

    assert credentials == []


def test_ensure_controller_urls_sets_urls_from_base_url():
    """
    arrange: A charm whose _base_url is an ingress URL.
    act: Call _ensure_controller_urls.
    assert: update_controller is called once with metadata/callback/webhook URLs derived from it.
    """
    charm = MagicMock(spec=GarmCharm)
    charm._base_url = "https://garm.example.com"
    auth_client = MagicMock()

    GarmCharm._ensure_controller_urls(charm, auth_client)

    auth_client.update_controller.assert_called_once_with(
        metadata_url="https://garm.example.com/api/v1/metadata",
        callback_url="https://garm.example.com/api/v1/callbacks",
        webhook_url="https://garm.example.com/webhooks",
    )


def test_ensure_controller_urls_strips_trailing_slash_from_base_url():
    """
    arrange: A charm whose _base_url is an ingress URL with a trailing slash.
    act: Call _ensure_controller_urls.
    assert: The pushed URLs have no double slashes in their paths.
    """
    charm = MagicMock(spec=GarmCharm)
    charm._base_url = "https://garm.example.com/"
    auth_client = MagicMock()

    GarmCharm._ensure_controller_urls(charm, auth_client)

    auth_client.update_controller.assert_called_once_with(
        metadata_url="https://garm.example.com/api/v1/metadata",
        callback_url="https://garm.example.com/api/v1/callbacks",
        webhook_url="https://garm.example.com/webhooks",
    )
