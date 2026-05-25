# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import render_garm_toml


def test_render_garm_toml_database_section():
    """
    arrange: Provide a db path.
    act: Render the GARM TOML config.
    assert: The [database] section uses sqlite3 with the given path.
    """
    result = render_garm_toml(
        listen_address="0.0.0.0",
        listen_port=9997,
        db_path="/srv/garm/data/garm.db",
        jwt_secret="abc123",
    )
    parsed = tomllib.loads(result)
    assert parsed["database"]["backend"] == "sqlite3"
    assert parsed["database"]["sqlite3"]["db_file"] == "/srv/garm/data/garm.db"


def test_render_garm_toml_apiserver_section():
    """
    arrange: Provide listen address and port.
    act: Render the GARM TOML config.
    assert: The [apiserver] section reflects the given address and port.
    """
    result = render_garm_toml(
        listen_address="127.0.0.1",
        listen_port=8080,
        db_path="/srv/garm/data/garm.db",
        jwt_secret="abc123",
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
        db_path="/srv/garm/data/garm.db",
        jwt_secret="mysecret",
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
        db_path="/srv/garm/data/garm.db",
        jwt_secret="abc123",
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
        db_path="/srv/garm/data/garm.db",
        jwt_secret="abc123",
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
# Secret management tests (no Harness needed — test the helper directly)
# ---------------------------------------------------------------------------


def test_generate_garm_secrets_returns_hex_strings():
    """
    arrange: Nothing.
    act: Call _generate_garm_secrets().
    assert: Returns a dict with jwt-secret as a 64-char hex string.
    """
    from charm import _generate_garm_secrets

    result = _generate_garm_secrets()
    assert set(result.keys()) == {"jwt-secret"}
    assert len(result["jwt-secret"]) == 64
    assert all(c in "0123456789abcdef" for c in result["jwt-secret"])


def test_generate_garm_secrets_produces_unique_values():
    """
    arrange: Nothing.
    act: Call _generate_garm_secrets() twice.
    assert: The two calls return different secrets.
    """
    from charm import _generate_garm_secrets

    first = _generate_garm_secrets()
    second = _generate_garm_secrets()
    assert first["jwt-secret"] != second["jwt-secret"]
