# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import string

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import _generate_garm_secrets, render_garm_toml


# ---------------------------------------------------------------------------
# render_garm_toml — PostgreSQL backend
# ---------------------------------------------------------------------------


def test_render_garm_toml_postgresql_backend():
    """
    arrange: Provide postgresql_config with connection parameters.
    act: Render the GARM TOML config.
    assert: The [database] section uses postgresql backend with correct fields.
    """
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        jwt_secret="test-secret",
        db_passphrase="a" * 32,
        postgresql_config={
            "username": "garm",
            "password": "secret",
            "hostname": "10.0.0.5",
            "port": 5432,
            "database": "garm_db",
            "sslmode": "require",
        },
    )
    parsed = tomllib.loads(result)
    assert parsed["database"]["backend"] == "postgresql"
    assert parsed["database"]["postgresql"]["hostname"] == "10.0.0.5"
    assert parsed["database"]["postgresql"]["username"] == "garm"
    assert parsed["database"]["postgresql"]["password"] == "secret"
    assert parsed["database"]["postgresql"]["port"] == 5432
    assert parsed["database"]["postgresql"]["database"] == "garm_db"
    assert parsed["database"]["postgresql"]["sslmode"] == "require"
    assert "sqlite3" not in parsed["database"]


def test_render_garm_toml_passphrase_in_database_section():
    """
    arrange: Provide a 32-char db_passphrase.
    act: Render the GARM TOML config.
    assert: The passphrase appears in the [database] section.
    """
    passphrase = "b" * 32
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        jwt_secret="test-secret",
        db_passphrase=passphrase,
        postgresql_config={
            "username": "u",
            "password": "p",
            "hostname": "h",
            "port": 5432,
            "database": "d",
            "sslmode": "disable",
        },
    )
    parsed = tomllib.loads(result)
    assert parsed["database"]["passphrase"] == passphrase


def test_render_garm_toml_sslmode_propagated():
    """
    arrange: Provide sslmode="verify-full" in postgresql_config.
    act: Render the GARM TOML config.
    assert: The sslmode is correctly set in the postgresql section.
    """
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        jwt_secret="test-secret",
        db_passphrase="c" * 32,
        postgresql_config={
            "username": "u",
            "password": "p",
            "hostname": "h",
            "port": 5432,
            "database": "d",
            "sslmode": "verify-full",
        },
    )
    parsed = tomllib.loads(result)
    assert parsed["database"]["postgresql"]["sslmode"] == "verify-full"


# ---------------------------------------------------------------------------
# render_garm_toml — other sections (unchanged behavior)
# ---------------------------------------------------------------------------


def test_render_garm_toml_apiserver_section():
    """
    arrange: Provide listen address and port.
    act: Render the GARM TOML config.
    assert: The [apiserver] section reflects the given address and port.
    """
    result = render_garm_toml(
        listen_address="127.0.0.1",
        listen_port=8080,
        jwt_secret="abc123",
        db_passphrase="d" * 32,
        postgresql_config={
            "username": "u",
            "password": "p",
            "hostname": "h",
            "port": 5432,
            "database": "d",
            "sslmode": "disable",
        },
    )
    parsed = tomllib.loads(result)
    assert parsed["apiserver"]["bind"] == "127.0.0.1"
    assert parsed["apiserver"]["port"] == 8080
    assert parsed["apiserver"]["use_tls"] is False


def test_render_garm_toml_jwt_auth_section():
    """
    arrange: Provide a jwt_secret.
    act: Render the GARM TOML config.
    assert: The [jwt_auth] section contains the secret.
    """
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        jwt_secret="mysecret",
        db_passphrase="e" * 32,
        postgresql_config={
            "username": "u",
            "password": "p",
            "hostname": "h",
            "port": 5432,
            "database": "d",
            "sslmode": "disable",
        },
    )
    parsed = tomllib.loads(result)
    assert parsed["jwt_auth"]["secret"] == "mysecret"
    assert parsed["jwt_auth"]["time_to_live"] == "8760h"


def test_render_garm_toml_metrics_section():
    """
    arrange: Any valid config inputs.
    act: Render the GARM TOML config.
    assert: The [metrics] section disables auth and enables metrics.
    """
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        jwt_secret="abc123",
        db_passphrase="f" * 32,
        postgresql_config={
            "username": "u",
            "password": "p",
            "hostname": "h",
            "port": 5432,
            "database": "d",
            "sslmode": "disable",
        },
    )
    parsed = tomllib.loads(result)
    assert parsed["metrics"]["disable_auth"] is True
    assert parsed["metrics"]["enable"] is True


def test_render_garm_toml_provider_section():
    """
    arrange: Any valid config inputs.
    act: Render the GARM TOML config.
    assert: The [[provider]] section has the OpenStack provider binary.
    """
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        jwt_secret="abc123",
        db_passphrase="g" * 32,
        postgresql_config={
            "username": "u",
            "password": "p",
            "hostname": "h",
            "port": 5432,
            "database": "d",
            "sslmode": "disable",
        },
    )
    parsed = tomllib.loads(result)
    assert len(parsed["provider"]) == 1
    provider = parsed["provider"][0]
    assert provider["name"] == "openstack"
    assert provider["provider_type"] == "external"
    assert (
        provider["external"]["provider_executable"]
        == "/usr/local/bin/garm-provider-openstack"
    )


# ---------------------------------------------------------------------------
# Secret management tests
# ---------------------------------------------------------------------------


def test_generate_garm_secrets_returns_jwt_and_passphrase():
    """
    arrange: Nothing.
    act: Call _generate_garm_secrets().
    assert: Returns a dict with jwt-secret (64-char hex) and db-passphrase (32-char alnum).
    """
    result = _generate_garm_secrets()
    assert "jwt-secret" in result
    assert "db-passphrase" in result
    # jwt-secret: 64-char hex
    assert len(result["jwt-secret"]) == 64
    assert all(c in "0123456789abcdef" for c in result["jwt-secret"])
    # db-passphrase: 32-char alphanumeric
    assert len(result["db-passphrase"]) == 32
    valid_chars = string.ascii_letters + string.digits
    assert all(c in valid_chars for c in result["db-passphrase"])


def test_generate_garm_secrets_produces_unique_values():
    """
    arrange: Nothing.
    act: Call _generate_garm_secrets() twice.
    assert: The two calls return different secrets.
    """
    first = _generate_garm_secrets()
    second = _generate_garm_secrets()
    assert first["jwt-secret"] != second["jwt-secret"]
    assert first["db-passphrase"] != second["db-passphrase"]
