# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the config-rendering and secret-generation helpers in charm.py.

These are the module-level functions GarmCharm.restart() composes: they take plain
arguments and return rendered content, so they are exercised directly. The charm's
event handling is tested through Scenario in test_charm.py.
"""

import os
import string
from unittest.mock import patch

import pytest
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import (
    _build_provider_list,
    _generate_admin_password,
    _generate_garm_secrets,
    _proxy_environment,
    render_garm_toml,
)

_DEFAULT_PG_CONFIG = {
    "username": "u",
    "password": "p",
    "hostname": "h",
    "port": 5432,
    "database": "d",
    "sslmode": "disable",
}

_PROVIDERS = [
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
    toml_content, provider_files = render_garm_toml(
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=_PROVIDERS,
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
    entries, provider_files = _build_provider_list(_PROVIDERS)
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
        providers=_PROVIDERS,
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
    toml_content, _ = render_garm_toml(
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config=_DEFAULT_PG_CONFIG,
        providers=_PROVIDERS[:1],
    )
    parsed = tomllib.loads(toml_content)

    for provider in parsed["provider"]:
        assert "environment_variables" not in provider["external"]


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
