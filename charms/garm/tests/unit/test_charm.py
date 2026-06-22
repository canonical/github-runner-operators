# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import os
import string
from unittest.mock import MagicMock, patch

import ops
import pytest
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import (
    GARM_ADMIN_CREDENTIALS_LABEL,
    GARM_SECRETS_LABEL,
    GarmCharm,
    _build_provider_list,
    _generate_admin_password,
    _generate_garm_secrets,
    _proxy_environment,
    render_garm_toml,
)
from garm_api import GarmConnectionError

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


def test_render_garm_toml_default_provider_when_no_providers_given():
    """
    arrange: No providers argument passed (defaults to None).
    act: render_garm_toml is called without providers.
    assert: The default "openstack" provider is rendered.
    """
    parsed = _render()
    assert len(parsed["provider"]) == 1
    assert parsed["provider"][0]["name"] == "openstack"


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


def test_build_provider_list_returns_default_when_none():
    """
    arrange: None is passed.
    act: _build_provider_list is called with None.
    assert: Returns the default single-entry list.
    """
    entries, files = _build_provider_list(None)
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


def test_proxy_environment_happy_path():
    """
    arrange: All three JUJU_CHARM_* proxy vars are set in the environment.
    act: Call _proxy_environment().
    assert: Returns both lower- and upper-case variants for each variable
            with the expected values.
    """
    env_vars = {
        "JUJU_CHARM_HTTP_PROXY": "http://proxy.example.com:3128",
        "JUJU_CHARM_HTTPS_PROXY": "https://proxy.example.com:3129",
        "JUJU_CHARM_NO_PROXY": "localhost,127.0.0.1",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        result = _proxy_environment()

    assert result["http_proxy"] == "http://proxy.example.com:3128"
    assert result["HTTP_PROXY"] == "http://proxy.example.com:3128"
    assert result["https_proxy"] == "https://proxy.example.com:3129"
    assert result["HTTPS_PROXY"] == "https://proxy.example.com:3129"
    assert result["no_proxy"] == "localhost,127.0.0.1"
    assert result["NO_PROXY"] == "localhost,127.0.0.1"
    assert len(result) == 6


@pytest.mark.parametrize(
    "env_vars,expected_keys",
    [
        # Empty string values are dropped entirely.
        (
            {
                "JUJU_CHARM_HTTP_PROXY": "",
                "JUJU_CHARM_HTTPS_PROXY": "",
                "JUJU_CHARM_NO_PROXY": "",
            },
            [],
        ),
        # Whitespace-only values are stripped and treated as empty.
        (
            {
                "JUJU_CHARM_HTTP_PROXY": "   ",
                "JUJU_CHARM_HTTPS_PROXY": "\t",
                "JUJU_CHARM_NO_PROXY": "  ",
            },
            [],
        ),
        # Nothing set → empty result.
        ({}, []),
        # Only http_proxy set → only that pair is present.
        (
            {"JUJU_CHARM_HTTP_PROXY": "http://proxy.example.com:3128"},
            ["http_proxy", "HTTP_PROXY"],
        ),
    ],
    ids=["all-empty", "all-whitespace", "nothing-set", "only-http"],
)
def test_proxy_environment_edge_cases(env_vars: dict, expected_keys: list):
    """
    arrange: Various incomplete or empty JUJU_CHARM_* configurations.
    act: Call _proxy_environment().
    assert: Only keys for non-empty values appear; empty/whitespace values
            are omitted.
    """
    with patch.dict(os.environ, env_vars, clear=True):
        result = _proxy_environment()

    assert set(result.keys()) == set(expected_keys)


def test_render_garm_toml_with_proxy_var_names():
    """
    arrange: Two provider configs and a non-empty proxy_var_names list.
    act: Call render_garm_toml() with proxy_var_names.
    assert: Every provider's external dict contains an environment_variables
            key equal to the supplied list.
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
    proxy_var_names = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ]
    toml_content, _ = render_garm_toml(
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=providers,
        proxy_var_names=proxy_var_names,
    )
    parsed = tomllib.loads(toml_content)

    for provider in parsed["provider"]:
        assert provider["external"]["environment_variables"] == proxy_var_names


def test_render_garm_toml_no_proxy_var_names_omits_key():
    """
    arrange: Provider configs but no proxy_var_names (default None).
    act: Call render_garm_toml() without proxy_var_names.
    assert: environment_variables is absent from every provider external dict
            (preserves existing behaviour; the existing assertion in
            test_render_garm_toml_with_configurator_providers also covers this).
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
    ]
    toml_content, _ = render_garm_toml(
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=providers,
    )
    parsed = tomllib.loads(toml_content)

    for provider in parsed["provider"]:
        assert "environment_variables" not in provider["external"]


def _make_restart_charm() -> MagicMock:
    """Build a minimal GarmCharm mock suitable for testing restart() proxy injection.

    Mirrors the mock setup pattern used by existing restart-related tests.
    The mock overrides _hash_toml and _get_on_disk_toml_hash so the actual
    hash logic runs without needing a real Pebble container.
    """
    charm = MagicMock()
    charm.is_ready.return_value = True
    charm.config.get.return_value = None

    # PostgreSQL relation data
    charm._get_postgresql_config.return_value = _DEFAULT_PG_CONFIG

    # GARM secrets
    charm._get_secrets.return_value = {
        "jwt-secret": "test-jwt-secret",
        "db-passphrase": "a" * 32,
    }

    # Configurator provider configs — one real provider so render succeeds.
    charm._get_configurator_provider_configs.return_value = [
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
        }
    ]

    # Wire the real hash function so hash assertions are meaningful.
    # _hash_toml is a staticmethod, so GarmCharm._hash_toml is already a plain
    # function — pass it directly as the side_effect.
    charm._hash_toml.side_effect = GarmCharm._hash_toml

    # No existing config on disk → the on-disk hash never matches, forcing the
    # replan path (the proxy comparison is short-circuited and irrelevant here).
    charm._get_on_disk_toml_hash.return_value = None
    mock_container = MagicMock()
    charm.unit.get_container.return_value = mock_container

    return charm


_SENTINEL = object()  # used to stop restart() execution before super().restart()


def _layer_service_env(charm: MagicMock) -> dict:
    """Return the app service environment from the layer captured by add_layer."""
    layer_arg = charm.unit.get_container.return_value.add_layer.call_args[0][1]
    return layer_arg["services"]["app"]["environment"]


def test_restart_proxy_vars_appear_in_pebble_layer():
    """
    arrange: JUJU_CHARM_HTTP_PROXY and JUJU_CHARM_HTTPS_PROXY are set; container
             has no existing config (forces replan path).
    act: Call GarmCharm.restart() with the charm mock, intercepting execution
         after add_layer via a sentinel exception raised by _maybe_first_run.
    assert: The Pebble layer passed to add_layer has the proxy vars in the
            service environment alongside config_hash.
    """
    proxy_env_vars = {
        "JUJU_CHARM_HTTP_PROXY": "http://proxy.example.com:3128",
        "JUJU_CHARM_HTTPS_PROXY": "https://proxy.example.com:3129",
    }
    charm = _make_restart_charm()
    # Raise after add_layer so we never reach super().restart(), which requires
    # self to be a real GarmCharm instance for the zero-arg super() check.
    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)

    with patch.dict(os.environ, proxy_env_vars, clear=True):
        with patch("charm.GarmApiClient"):
            with pytest.raises(StopIteration):
                GarmCharm.restart(charm)

    charm.unit.get_container.return_value.add_layer.assert_called_once()
    service_env = _layer_service_env(charm)

    assert service_env["http_proxy"] == "http://proxy.example.com:3128"
    assert service_env["HTTP_PROXY"] == "http://proxy.example.com:3128"
    assert service_env["https_proxy"] == "https://proxy.example.com:3129"
    assert service_env["HTTPS_PROXY"] == "https://proxy.example.com:3129"
    assert "config_hash" in service_env


def test_restart_replans_when_only_proxy_value_changes():
    """
    arrange: The on-disk TOML is unchanged, but the proxy value applied in the
             running plan differs from the newly configured one (same whitelist,
             so the config hash is identical).
    act: Call restart().
    assert: A new layer is still applied -- the proxy value is compared against
            the plan, not the on-disk config, so a value-only change replans.
    """
    charm = _make_restart_charm()
    old_proxy = {"JUJU_CHARM_HTTP_PROXY": "http://old.example.com:3128"}
    new_proxy = {"JUJU_CHARM_HTTP_PROXY": "http://new.example.com:3128"}

    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)
    with patch.dict(os.environ, old_proxy, clear=True):
        with patch("charm.GarmApiClient"):
            with pytest.raises(StopIteration):
                GarmCharm.restart(charm)
    applied_env = _layer_service_env(charm)
    applied_hash = applied_env["config_hash"]
    applied_proxy = {k: v for k, v in applied_env.items() if k != "config_hash"}

    charm.unit.get_container.return_value.add_layer.reset_mock()
    charm._get_on_disk_toml_hash.return_value = applied_hash
    charm._get_applied_proxy_env.return_value = applied_proxy
    with patch.dict(os.environ, new_proxy, clear=True):
        with patch("charm.GarmApiClient"):
            with pytest.raises(StopIteration):
                GarmCharm.restart(charm)

    charm.unit.get_container.return_value.add_layer.assert_called_once()


def test_restart_no_proxy_hash_matches_on_disk_format():
    """
    arrange: No proxy vars are set; the charm renders config for one provider.
    act: Run restart() and capture the config_hash it computes.
    assert: It equals the hash of the rendered config in _get_on_disk_toml_hash's
            format, so an unchanged config never triggers a spurious replan.
    """
    charm = _make_restart_charm()
    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)

    with patch.dict(os.environ, {}, clear=True):
        with patch("charm.GarmApiClient"):
            with pytest.raises(StopIteration):
                GarmCharm.restart(charm)
    captured = _layer_service_env(charm)["config_hash"]

    toml_content, provider_files = render_garm_toml(
        jwt_secret="test-jwt-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=charm._get_configurator_provider_configs.return_value,
    )
    expected_input = (
        toml_content
        + "\n"
        + "\n".join(f"{path}\n{content}" for path, content in sorted(provider_files.items()))
    )
    assert captured == GarmCharm._hash_toml(expected_input)


def test_render_garm_toml_default_provider_applies_proxy_var_names():
    """
    arrange: No configurator providers but a non-empty proxy_var_names list.
    act: Call render_garm_toml() with providers=None and proxy_var_names.
    assert: The default openstack provider forwards the proxy var names via
            environment_variables (consistent with the per-provider path).
    """
    proxy_var_names = ["http_proxy", "HTTP_PROXY"]
    toml_content, _ = render_garm_toml(
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        proxy_var_names=proxy_var_names,
    )
    parsed = tomllib.loads(toml_content)

    assert parsed["provider"][0]["external"]["environment_variables"] == proxy_var_names


def test_restart_skips_replan_when_config_and_proxy_unchanged():
    """
    arrange: First apply records the config_hash and proxy env; the plan then
             reports the same on-disk config and the same applied proxy.
    act: Call restart() a second time with the identical proxy/config.
    assert: No new layer is added -- nothing changed, so the service is left
            running undisturbed.
    """
    charm = _make_restart_charm()
    proxy_env = {"JUJU_CHARM_HTTP_PROXY": "http://proxy.example.com:3128"}

    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)
    with patch.dict(os.environ, proxy_env, clear=True):
        with patch("charm.GarmApiClient"):
            with pytest.raises(StopIteration):
                GarmCharm.restart(charm)
    applied_env = _layer_service_env(charm)
    applied_hash = applied_env["config_hash"]
    applied_proxy = {k: v for k, v in applied_env.items() if k != "config_hash"}

    charm.unit.get_container.return_value.add_layer.reset_mock()
    charm._get_on_disk_toml_hash.return_value = applied_hash
    charm._get_applied_proxy_env.return_value = applied_proxy
    charm._maybe_first_run.side_effect = None
    with patch.dict(os.environ, proxy_env, clear=True):
        with patch("charm.GarmApiClient"):
            GarmCharm.restart(charm)

    charm.unit.get_container.return_value.add_layer.assert_not_called()


def test_get_applied_proxy_env_returns_proxy_vars():
    """
    arrange: The Pebble plan reports the app service whose env holds config_hash
             alongside proxy vars.
    act: Call _get_applied_proxy_env().
    assert: Only the proxy vars are returned; config_hash is excluded.
    """
    charm = MagicMock()
    service = MagicMock()
    service.environment = {
        "config_hash": "deadbeef",
        "http_proxy": "http://proxy.example.com:3128",
        "HTTP_PROXY": "http://proxy.example.com:3128",
    }
    charm.unit.get_container.return_value.get_plan.return_value.services = {"app": service}

    assert GarmCharm._get_applied_proxy_env(charm) == {
        "http_proxy": "http://proxy.example.com:3128",
        "HTTP_PROXY": "http://proxy.example.com:3128",
    }


def test_get_applied_proxy_env_returns_empty_when_service_absent():
    """
    arrange: The Pebble plan has no app service yet.
    act: Call _get_applied_proxy_env().
    assert: An empty dict is returned, treated as "no proxy applied".
    """
    charm = MagicMock()
    charm.unit.get_container.return_value.get_plan.return_value.services = {}

    assert GarmCharm._get_applied_proxy_env(charm) == {}
