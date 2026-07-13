# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import os
import string
from unittest.mock import MagicMock, PropertyMock, patch

import ops
import pytest
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

import garm_template
from charm import (
    GARM_ADMIN_CREDENTIALS_LABEL,
    GARM_PORT,
    GARM_SECRETS_LABEL,
    GarmCharm,
    _build_provider_list,
    _generate_admin_password,
    _generate_garm_secrets,
    _proxy_environment,
    render_garm_toml,
)
from garm_api import GarmApiError, GarmConnectionError
from github_reconciler import DEFAULT_GITHUB_ENDPOINT
from scaleset_reconciler import ScalesetSpec

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


def test_ensure_secrets_creates_secrets_on_first_run():
    """
    arrange: Leader unit; neither garm-secrets nor garm-admin-credentials exist.
    act: Call _ensure_secrets().
    assert: Both secrets are created and labelled correctly.
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


_RESTART_PROVIDER_CONFIGS = [
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


def _plan_with_service_env(environment: dict | None) -> ops.pebble.Plan:
    """Build a Pebble plan whose 'app' service carries the given environment.

    Passing None yields an empty plan (no 'app' service), which models a
    container that has never been configured — previous_hash resolves to None.
    """
    if environment is None:
        return ops.pebble.Plan()
    plan = ops.pebble.Plan()
    plan.services["app"] = ops.pebble.Service(
        "app",
        {"override": "replace", "command": "x", "environment": environment},
    )
    return plan


def _expected_config_hash(proxy_env: dict, providers: list | None = None) -> str:
    """Reproduce restart()'s hash-input construction for assertion purposes.

    Mirrors the exact serialization restart() feeds into _hash_toml: the
    rendered TOML, the sorted provider files, then — only when a proxy is
    configured — the sorted proxy env key=value pairs.
    """
    providers = _RESTART_PROVIDER_CONFIGS if providers is None else providers
    toml_content, provider_files = render_garm_toml(
        jwt_secret="test-jwt-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=providers,
        proxy_var_names=sorted(proxy_env.keys()),
    )
    hash_input = (
        toml_content
        + "\n"
        + "\n".join(f"{path}\n{content}" for path, content in sorted(provider_files.items()))
    )
    if proxy_env:
        hash_input += "\n" + "\n".join(f"{k}={v}" for k, v in sorted(proxy_env.items()))
    return GarmCharm._hash_toml(hash_input)


def _make_restart_charm(previous_plan_env: dict | None = None) -> MagicMock:
    """Build a minimal GarmCharm mock suitable for testing restart() proxy injection.

    Mirrors the mock setup pattern used by existing restart-related tests.
    The mock wires the real _hash_toml so the actual hash logic runs, and
    seeds the container's current Pebble plan (the source of previous_hash)
    from ``previous_plan_env``; None models a never-configured container.
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
    charm._get_configurator_provider_configs.return_value = list(_RESTART_PROVIDER_CONFIGS)

    # Wire the real hash function so hash assertions are meaningful.
    # _hash_toml is a staticmethod, so GarmCharm._hash_toml is already a plain
    # function — pass it directly as the side_effect.
    charm._hash_toml.side_effect = GarmCharm._hash_toml

    # _current_config_hash is a staticmethod; run the real plan-reading logic
    # against the seeded container plan (the source of previous_hash).
    charm._current_config_hash.side_effect = GarmCharm._current_config_hash

    mock_container = MagicMock()
    mock_container.get_plan.return_value = _plan_with_service_env(previous_plan_env)
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


def test_restart_no_proxy_hash_matches_rendered_config():
    """
    arrange: No proxy vars are set; the charm renders config for one provider.
    act: Run restart() and capture the config_hash it computes.
    assert: It equals the hash of the rendered config folded with the (empty)
            proxy env, so an unchanged config never triggers a spurious replan.
    """
    charm = _make_restart_charm()
    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)

    with patch.dict(os.environ, {}, clear=True):
        with patch("charm.GarmApiClient"):
            with pytest.raises(StopIteration):
                GarmCharm.restart(charm)
    captured = _layer_service_env(charm)["config_hash"]

    assert captured == _expected_config_hash({})


def test_restart_proxy_value_change_forces_layer_rewrite():
    """
    arrange: The container's current plan already carries a config_hash and an
             http_proxy value computed from proxy value A; the model proxy is
             now value B (same variable set, only the value changed).
    act: Run restart().
    assert: The rewritten layer's service environment reflects value B, i.e. a
            proxy-value-only change is detected and replanned.
    """
    old_env = {"JUJU_CHARM_HTTP_PROXY": "http://proxy-a.example.com:3128"}
    new_env = {"JUJU_CHARM_HTTP_PROXY": "http://proxy-b.example.com:3128"}
    with patch.dict(os.environ, old_env, clear=True):
        old_proxy = _proxy_environment()
    old_hash = _expected_config_hash(old_proxy)

    charm = _make_restart_charm(previous_plan_env={"config_hash": old_hash, **old_proxy})
    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)

    with (
        patch.dict(os.environ, new_env, clear=True),
        patch("charm.GarmApiClient"),
        pytest.raises(StopIteration),
    ):
        GarmCharm.restart(charm)

    charm.unit.get_container.return_value.add_layer.assert_called_once()
    service_env = _layer_service_env(charm)
    assert service_env["http_proxy"] == "http://proxy-b.example.com:3128"
    assert service_env["HTTP_PROXY"] == "http://proxy-b.example.com:3128"


def test_restart_clearing_proxy_removes_it_from_layer():
    """
    arrange: The container's current plan carries a proxy value; the model proxy
             is now cleared (empty).
    act: Run restart().
    assert: The rewritten layer's service environment no longer contains the
            proxy keys.
    """
    old_env = {"JUJU_CHARM_HTTP_PROXY": "http://proxy-a.example.com:3128"}
    with patch.dict(os.environ, old_env, clear=True):
        old_proxy = _proxy_environment()
    old_hash = _expected_config_hash(old_proxy)

    charm = _make_restart_charm(previous_plan_env={"config_hash": old_hash, **old_proxy})
    charm._maybe_first_run.side_effect = StopIteration(_SENTINEL)

    with (
        patch.dict(os.environ, {}, clear=True),
        patch("charm.GarmApiClient"),
        pytest.raises(StopIteration),
    ):
        GarmCharm.restart(charm)

    charm.unit.get_container.return_value.add_layer.assert_called_once()
    service_env = _layer_service_env(charm)
    assert "http_proxy" not in service_env
    assert "HTTP_PROXY" not in service_env


def test_restart_unchanged_config_skips_replan():
    """
    arrange: The container's current plan already stores the config_hash that
             the current state (same proxy, same config) renders to.
    act: Run restart().
    assert: The early-return path is taken — no new layer is added and the
            service is not replanned — while runners are still reconciled.
    """
    proxy_env = {"JUJU_CHARM_HTTP_PROXY": "http://proxy.example.com:3128"}
    with patch.dict(os.environ, proxy_env, clear=True):
        current_proxy = _proxy_environment()
    current_hash = _expected_config_hash(current_proxy)

    charm = _make_restart_charm(previous_plan_env={"config_hash": current_hash, **current_proxy})

    with (
        patch.dict(os.environ, proxy_env, clear=True),
        patch("charm.GarmApiClient"),
    ):
        GarmCharm.restart(charm)

    charm.unit.get_container.return_value.add_layer.assert_not_called()
    charm.unit.get_container.return_value.replan.assert_not_called()
    charm._reconcile_runners.assert_called_once()


def test_restart_without_configurator_relation_still_prunes_orphaned_scalesets():
    """
    arrange: The charm is ready (postgres + secrets available) but the
             garm-configurator relation is gone, so there are no provider configs
             and get_relation returns None.
    act: Run restart().
    assert: _reconcile_runners() still runs so ScalesetReconciler can delete the
            now-orphaned scalesets, the workload is not replanned, and the unit
            reports that it is waiting for the garm-configurator relation.
    """
    charm = _make_restart_charm()
    charm._get_configurator_provider_configs.return_value = []
    charm.model.get_relation.return_value = None

    with patch.dict(os.environ, {}, clear=True):
        GarmCharm.restart(charm)

    charm._reconcile_runners.assert_called_once()
    charm.unit.get_container.return_value.add_layer.assert_not_called()
    charm.update_app_and_unit_status.assert_called_once_with(
        ops.WaitingStatus("Waiting for garm-configurator relation")
    )


def test_restart_configurator_relation_present_but_unpopulated_does_not_prune():
    """
    arrange: The charm is ready but the garm-configurator relation, though still
             present, has not yet published its secret-dependent fields, so there
             are no provider configs while get_relation returns the relation.
    act: Run restart().
    assert: _reconcile_runners() is NOT called — pruning against the empty desired
            state would delete live scalesets — the workload is not replanned, and
            the unit waits for the relation to finish publishing.
    """
    charm = _make_restart_charm()
    charm._get_configurator_provider_configs.return_value = []
    charm.model.get_relation.return_value = MagicMock()

    with patch.dict(os.environ, {}, clear=True):
        GarmCharm.restart(charm)

    charm._reconcile_runners.assert_not_called()
    charm.unit.get_container.return_value.add_layer.assert_not_called()
    charm.update_app_and_unit_status.assert_called_once_with(
        ops.WaitingStatus("Waiting for garm-configurator relation")
    )


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


def test_reconcile_runners_reconciles_credentials_entities_then_scalesets():
    """
    arrange: Admin credentials are available and the desired credential/entity/scaleset specs are
        stubbed.
    act: Call _reconcile_runners().
    assert: On a single authenticated client it configures controller URLs, then reconciles
        credentials, entities, and scalesets in that dependency order, reports ActiveStatus, and
        never restarts.
    """
    charm = object.__new__(GarmCharm)
    charm._get_admin_credentials = MagicMock(
        return_value={"username": "admin", "password": "TestPass-123!"}
    )
    credentials = [object()]
    entities = [object()]
    scalesets = [object()]
    charm._build_desired_credentials = MagicMock(return_value=credentials)
    charm._build_desired_scalesets = MagicMock(return_value=scalesets)
    charm._ensure_controller_urls = MagicMock()
    charm.restart = MagicMock()

    with (
        patch("charm.GarmAuthenticatedClient") as mock_auth_cls,
        patch("charm.GithubReconciler") as mock_github_cls,
        patch("charm.EntityReconciler") as mock_entity_cls,
        patch("charm.ScalesetReconciler") as mock_scaleset_cls,
        patch("charm._apply_garm_template", return_value=99) as mock_apply,
        patch("charm.CharmState") as mock_charm_state_cls,
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
        patch.object(GarmCharm, "app", new_callable=PropertyMock) as mock_app,
    ):
        mock_charm_state_cls.from_charm.return_value.ssh_debug_connections = []
        mock_charm_state_cls.from_charm.return_value.desired_entities = entities
        mock_unit.return_value = MagicMock()
        mock_app.return_value = MagicMock()
        order = MagicMock()
        order.attach_mock(mock_github_cls.return_value.reconcile, "github")
        order.attach_mock(mock_entity_cls.return_value.reconcile, "entity")
        order.attach_mock(mock_scaleset_cls.return_value.reconcile, "scaleset")
        charm._reconcile_runners()

    expected_url = f"http://127.0.0.1:{GARM_PORT}/api/v1"
    mock_auth_cls.from_login.assert_called_once_with(expected_url, "admin", "TestPass-123!")
    auth_client = mock_auth_cls.from_login.return_value
    # Controller URLs must be configured before any operational call, or GARM returns 409.
    charm._ensure_controller_urls.assert_called_once_with(auth_client)
    # Each reconciler must be built against the same authenticated client.
    mock_github_cls.assert_called_once_with(auth_client)
    mock_entity_cls.assert_called_once_with(auth_client)
    mock_apply.assert_called_once()
    charm._build_desired_scalesets.assert_called_once_with(99)
    mock_scaleset_cls.assert_called_once_with(auth_client)
    mock_github_cls.return_value.reconcile.assert_called_once_with(credentials)
    mock_entity_cls.return_value.reconcile.assert_called_once_with(entities)
    mock_scaleset_cls.return_value.reconcile.assert_called_once_with(scalesets)
    # Entities depend on credentials and scalesets depend on entities, so order matters.
    assert [name for name, _, _ in order.mock_calls] == ["github", "entity", "scaleset"]
    charm.restart.assert_not_called()


def test_reconcile_runners_charmed_template_error_sets_waiting_status():
    """
    arrange: Admin credentials are available but _apply_garm_template raises CharmedTemplateError.
    act: Call _reconcile_runners().
    assert: The unit degrades to WaitingStatus carrying the error message (not an error state),
        and scalesets are never reconciled.
    """
    charm = object.__new__(GarmCharm)
    charm._get_admin_credentials = MagicMock(
        return_value={"username": "admin", "password": "TestPass-123!"}
    )
    charm._build_desired_credentials = MagicMock(return_value=[])
    charm._build_desired_scalesets = MagicMock(return_value=[])
    charm._ensure_controller_urls = MagicMock()

    with (
        patch("charm.GarmAuthenticatedClient"),
        patch("charm.GithubReconciler"),
        patch("charm.ScalesetReconciler") as mock_scaleset_cls,
        patch(
            "charm._apply_garm_template",
            side_effect=garm_template.CharmedTemplateError("base template missing"),
        ),
        patch("charm.CharmState") as mock_state,
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
        patch.object(GarmCharm, "app", new_callable=PropertyMock) as mock_app,
    ):
        mock_state.from_charm.return_value.ssh_debug_connections = []
        mock_unit.return_value = MagicMock()
        mock_app.return_value = MagicMock()
        charm._reconcile_runners()  # must not raise

        status = mock_unit.return_value.status
        mock_scaleset_cls.return_value.reconcile.assert_not_called()

    assert isinstance(status, ops.WaitingStatus)
    assert status.message == "base template missing"


def test_reconcile_runners_success_refreshes_stale_app_status():
    """
    arrange: A stale app status and a reconcile that will succeed.
    act: Call _reconcile_runners().
    assert: Both unit and app status refresh to ActiveStatus.
    """
    charm = object.__new__(GarmCharm)
    charm._get_admin_credentials = MagicMock(
        return_value={"username": "admin", "password": "TestPass-123!"}
    )
    charm._build_desired_credentials = MagicMock(return_value=[])
    charm._build_desired_scalesets = MagicMock(return_value=[])
    charm._ensure_controller_urls = MagicMock()

    with (
        patch("charm.GarmAuthenticatedClient"),
        patch("charm.GithubReconciler"),
        patch("charm.EntityReconciler"),
        patch("charm.ScalesetReconciler"),
        patch("charm._apply_garm_template", return_value=99),
        patch("charm.CharmState") as mock_charm_state_cls,
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
        patch.object(GarmCharm, "app", new_callable=PropertyMock) as mock_app,
    ):
        mock_charm_state_cls.from_charm.return_value.ssh_debug_connections = []
        mock_charm_state_cls.from_charm.return_value.desired_entities = []
        mock_unit.return_value = MagicMock()
        mock_unit.return_value.is_leader.return_value = True
        mock_unit.return_value.status = ops.WaitingStatus("Waiting for pebble ready")
        mock_app.return_value = MagicMock()
        mock_app.return_value.status = ops.WaitingStatus("Waiting for pebble ready")

        charm._reconcile_runners()

        unit_status = mock_unit.return_value.status
        app_status = mock_app.return_value.status

    assert unit_status == ops.ActiveStatus()
    assert app_status == ops.ActiveStatus()


def test_restart_missing_configurator_relation_refreshes_stale_app_status():
    """
    arrange: A stale app status and a missing garm-configurator relation.
    act: Call restart().
    assert: Both unit and app status become "Waiting for garm-configurator relation".
    """
    charm = object.__new__(GarmCharm)
    charm._ensure_secrets = MagicMock()
    charm.is_ready = MagicMock(return_value=True)
    charm._get_postgresql_config = MagicMock(return_value=_DEFAULT_PG_CONFIG)
    charm._get_secrets = MagicMock(
        return_value={"jwt-secret": "test-jwt-secret", "db-passphrase": "a" * 32}
    )
    charm._get_configurator_provider_configs = MagicMock(return_value=[])
    # restart() now still prunes orphaned scalesets when the relation is gone;
    # stub it out since this test only cares about the status it reports.
    charm._reconcile_runners = MagicMock()

    with (
        patch.object(GarmCharm, "config", new_callable=PropertyMock) as mock_config,
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
        patch.object(GarmCharm, "app", new_callable=PropertyMock) as mock_app,
        patch.object(GarmCharm, "model", new_callable=PropertyMock) as mock_model,
    ):
        mock_config.return_value = {}
        mock_unit.return_value = MagicMock()
        mock_unit.return_value.is_leader.return_value = True
        mock_unit.return_value.status = ops.WaitingStatus("Waiting for pebble ready")
        mock_app.return_value = MagicMock()
        mock_app.return_value.status = ops.WaitingStatus("Waiting for pebble ready")
        mock_model.return_value.get_relation.return_value = None

        charm.restart()

        unit_status = mock_unit.return_value.status
        app_status = mock_app.return_value.status

    assert unit_status == ops.WaitingStatus("Waiting for garm-configurator relation")
    assert app_status == ops.WaitingStatus("Waiting for garm-configurator relation")


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
    assert cred.private_key == "PEMDATA"
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
