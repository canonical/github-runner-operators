# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import string

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import _build_provider_list, _generate_garm_secrets, render_garm_toml

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
        "listen_address": "0.0.0.0",
        "listen_port": 9997,
        "jwt_secret": "test-secret",
        "db_passphrase": "a" * 32,
        "postgresql_config": _DEFAULT_PG_CONFIG,
    }
    kwargs.update(overrides)
    return tomllib.loads(render_garm_toml(**kwargs))


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
        ("apiserver", "bind", "127.0.0.1", {"listen_address": "127.0.0.1"}),
        ("apiserver", "port", 8080, {"listen_port": 8080}),
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
    assert (
        provider["external"]["provider_executable"]
        == "/usr/local/bin/garm-provider-openstack"
    )


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
    assert: Two [[provider]] blocks are rendered with correct names and env vars.
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
            "image_id": "img-1",
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
            "image_id": "img-2",
        },
    ]
    parsed = _render(providers=providers)
    assert len(parsed["provider"]) == 2

    p0 = parsed["provider"][0]
    assert p0["name"] == "garm-configurator-0"
    assert p0["external"]["provider_executable"] == "/usr/local/bin/garm-provider-openstack"
    env_vars = p0["external"]["environment_variables"]
    assert "OPENSTACK_AUTH_URL=https://ks1.example.com:5000/v3" in env_vars
    assert "OPENSTACK_USERNAME=admin1" in env_vars
    assert "OPENSTACK_PASSWORD=pass1" in env_vars
    assert "OPENSTACK_PROJECT_NAME=proj1" in env_vars
    assert "OPENSTACK_IMAGE_ID=img-1" in env_vars

    p1 = parsed["provider"][1]
    assert p1["name"] == "garm-configurator-1"
    env_vars_1 = p1["external"]["environment_variables"]
    assert "OPENSTACK_USERNAME=admin2" in env_vars_1


def test_build_provider_list_returns_default_when_empty():
    """
    arrange: An empty list is passed.
    act: _build_provider_list is called.
    assert: Returns the default single-entry list with "openstack" provider.
    """
    result = _build_provider_list([])
    assert len(result) == 1
    assert result[0]["name"] == "openstack"


def test_build_provider_list_returns_default_when_none():
    """
    arrange: None is passed.
    act: _build_provider_list is called with None.
    assert: Returns the default single-entry list.
    """
    result = _build_provider_list(None)
    assert len(result) == 1
    assert result[0]["name"] == "openstack"
