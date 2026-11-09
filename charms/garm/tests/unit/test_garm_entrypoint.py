#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the GARM entrypoint script."""

import json
import logging
import os
from unittest.mock import patch

import pytest

import garm_entrypoint

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

_LXD_PROVIDER = {
    "unit_name": "garm-configurator-0",
    "provider_type": "lxd",
    "lxd_api_url": "https://lxd.example.com:8443",
    "lxd_project_name": "runners",
    "lxd_instance_type": "container",
    "lxd_secure_boot": True,
    "lxd_client_certificate": "client-certificate",
    "lxd_client_key": "client-key",
    "lxd_server_certificate": "server-certificate",
}


def test_render_garm_config_full():
    """arrange: All required and optional environment variables are set.

    act: Render the GARM config.
    assert: The TOML includes the database block, API server config, JWT and metrics.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "10.0.0.5",
        "POSTGRESQL_DB_USERNAME": "garm",
        "POSTGRESQL_DB_PASSWORD": "pw",
        "GARM_JWT_SECRET": "secret",
        "GARM_PASSPHRASE": "pass" * 8,
        "POSTGRESQL_DB_PORT": "5433",
        "POSTGRESQL_DB_NAME": "garmdb",
        "APP_BASE_URL": "https://example.com",
        "GARM_PROVIDERS_JSON": '[{"unit_name":"provider-0","auth_url":"https://keystone","username":"u","password":"p","project_name":"prj","user_domain_name":"Default","project_domain_name":"Default","region_name":"RegionOne","network":"private"}]',
    }

    with patch.dict(os.environ, env, clear=True):
        config = garm_entrypoint.render_garm_config(env)

    assert 'hostname = "10.0.0.5"' in config
    assert "port = 5433" in config
    assert 'username = "garm"' in config
    assert 'password = "pw"' in config
    assert 'database = "garmdb"' in config
    assert 'secret = "secret"' in config
    assert 'passphrase = "passpasspasspasspasspasspasspass"' in config
    assert 'metadata_url = "https://example.com/api/v1/metadata"' in config
    assert 'callback_url = "https://example.com/api/v1/callbacks"' in config
    assert 'name = "provider-0"' in config
    assert 'config_file = "/etc/garm/provider-provider-0.toml"' in config


def test_render_garm_config_defaults():
    """arrange: Only required variables are set.

    act: Render the GARM config.
    assert: Optional DB port and name use defaults and no provider section is rendered.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
    }
    with patch.dict(os.environ, env, clear=True):
        config = garm_entrypoint.render_garm_config(env)

    assert "port = 5432" in config
    assert 'database = "garm"' in config


def test_missing_required_variable_exits(caplog):
    """arrange: Required variables are missing.

    act: Run main.
    assert: The script exits non-zero and reports the missing variables.
    """
    with (
        caplog.at_level(logging.ERROR),
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(SystemExit) as exc_info,
    ):
        garm_entrypoint.main()

    assert exc_info.value.code != 0
    assert "Missing required environment variables" in caplog.text


def test_invalid_database_port_exits(caplog, monkeypatch, tmp_path):
    """arrange: PostgreSQL port is not an integer.

    act: Run main.
    assert: The entrypoint reports a configuration error and does not exec GARM.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
        "POSTGRESQL_DB_PORT": "not-a-port",
    }
    monkeypatch.setattr(garm_entrypoint, "GARM_CONFIG_PATH", tmp_path / "config.toml")

    with (
        caplog.at_level(logging.ERROR),
        patch.dict(os.environ, env, clear=True),
        pytest.raises(SystemExit) as exc_info,
    ):
        garm_entrypoint.main()

    assert exc_info.value.code == 1
    assert "POSTGRESQL_DB_PORT must be an integer" in caplog.text


@patch("garm_entrypoint.os.execvp")
@patch("garm_entrypoint.os.chmod")
def test_main_writes_config_and_execs(mock_chmod, mock_execvp, monkeypatch, tmp_path):
    """arrange: Environment variables are set.

    act: Run main.
    assert: config.toml is written and the GARM binary is exec'd.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
    }
    config_path = tmp_path / "config.toml"
    provider_dir = tmp_path / "provider"
    monkeypatch.setattr(garm_entrypoint, "GARM_CONFIG_PATH", config_path)
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)
    with patch.dict(os.environ, env, clear=True):
        garm_entrypoint.main()

    assert config_path.exists()
    mock_chmod.assert_called_once_with(config_path, 0o600)
    mock_execvp.assert_called_once_with(
        "/usr/local/bin/garm", ["garm", "--config", str(config_path)]
    )


@patch("garm_entrypoint.os.execvp")
@patch("garm_entrypoint.os.chmod")
def test_main_scrubs_sensitive_env_before_exec(mock_chmod, mock_execvp, monkeypatch, tmp_path):
    """arrange: Sensitive config is provided through environment variables.

    act: Run main.
    assert: Sensitive values are removed from the process environment before exec.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
    }
    config_path = tmp_path / "config.toml"
    provider_dir = tmp_path / "provider"
    monkeypatch.setattr(garm_entrypoint, "GARM_CONFIG_PATH", config_path)
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)
    with patch.dict(os.environ, env, clear=True):
        garm_entrypoint.main()

        assert "POSTGRESQL_DB_USERNAME" not in os.environ
        assert "POSTGRESQL_DB_PASSWORD" not in os.environ
        assert "GARM_JWT_SECRET" not in os.environ
        assert "GARM_PASSPHRASE" not in os.environ

    mock_chmod.assert_called_once_with(config_path, 0o600)
    mock_execvp.assert_called_once_with(
        "/usr/local/bin/garm", ["garm", "--config", str(config_path)]
    )


@patch("garm_entrypoint.os.execvp")
def test_main_logs_clean_exit_on_config_error(mock_execvp, caplog, monkeypatch, tmp_path):
    """arrange: Provider JSON is malformed.

    act: Run main.
    assert: The script logs one error line and exits cleanly.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
        "GARM_PROVIDERS_JSON": "not-json",
    }
    config_path = tmp_path / "config.toml"
    provider_dir = tmp_path / "provider"
    monkeypatch.setattr(garm_entrypoint, "GARM_CONFIG_PATH", config_path)
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)

    with (
        caplog.at_level(logging.ERROR),
        patch.dict(os.environ, env, clear=True),
        pytest.raises(SystemExit) as exc_info,
    ):
        garm_entrypoint.main()

    assert exc_info.value.code == 1
    assert "Failed to prepare GARM configuration" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text
    mock_execvp.assert_not_called()


@patch("garm_entrypoint.os.execvp")
def test_main_rewrites_config_and_execs(mock_execvp, monkeypatch, tmp_path):
    """arrange: Environment variables describe the complete GARM configuration.

    act: Run main.
    assert: The entrypoint rewrites config.toml and execs GARM.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
    }
    config_path = tmp_path / "config.toml"
    provider_dir = tmp_path / "provider"
    monkeypatch.setattr(garm_entrypoint, "GARM_CONFIG_PATH", config_path)
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)
    with patch.dict(os.environ, env, clear=True):
        garm_entrypoint.main()

    mock_execvp.assert_called_once_with(
        "/usr/local/bin/garm", ["garm", "--config", str(config_path)]
    )


def test_provider_unit_name_cannot_escape_config_directory():
    """arrange: Provider data contains a path traversal unit name.

    act: Build the provider configuration.
    assert: The untrusted name is rejected before any file path is created.
    """
    with pytest.raises(
        garm_entrypoint.InvalidConfigurationError, match="Invalid provider unit name"
    ):
        garm_entrypoint._build_provider_files({"GARM_PROVIDERS_JSON": '[{"unit_name": "../x"}]'})


def test_toml_string_escaping():
    """arrange: Password contains characters that need TOML escaping.

    act: Render the config.
    assert: Special characters are escaped correctly in the output.
    """
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": 'user"with\\quotes',
        "POSTGRESQL_DB_PASSWORD": "pass",
        "GARM_JWT_SECRET": "secret",
        "GARM_PASSPHRASE": "pass" * 8,
    }
    with patch.dict(os.environ, env, clear=True):
        config = garm_entrypoint.render_garm_config(env)

    assert 'username = "user\\"with\\\\quotes"' in config


def test_build_lxd_provider_writes_config_and_certificate_files(monkeypatch, tmp_path):
    """arrange: A configurator publishes an LXD provider with all three certificates.

    act: Build the provider files.
    assert: The provider runs the LXD binary with a TOML config pointing at the written
        certificate files and the default ubuntu image remote.
    """
    provider_dir = tmp_path / "provider"
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)

    entries, files = garm_entrypoint._build_provider_files(
        {"GARM_PROVIDERS_JSON": json.dumps([_LXD_PROVIDER])}
    )

    entry = entries[0]
    assert entry["description"] == "LXD provider (garm-configurator-0)"
    assert entry["external"]["provider_executable"] == "/usr/local/bin/garm-provider-lxd"

    config_path = provider_dir / "provider-garm-configurator-0.toml"
    config = tomllib.loads(files[str(config_path)])
    assert config["url"] == "https://lxd.example.com:8443"
    assert config["project_name"] == "runners"
    assert config["instance_type"] == "container"
    assert config["secure_boot"] is True
    assert config["unix_socket_path"] == ""
    assert config["include_default_profile"] is False
    assert config["client_certificate"].endswith("provider-garm-configurator-0-client.crt")
    assert config["client_key"].endswith("provider-garm-configurator-0-client.key")
    assert config["tls_server_certificate"].endswith("provider-garm-configurator-0-server.crt")
    assert config["image_remotes"] == {
        "ubuntu": {
            "addr": "https://cloud-images.ubuntu.com/releases",
            "public": True,
            "protocol": "simplestreams",
            "skip_verify": False,
        }
    }
    assert files[str(provider_dir / "provider-garm-configurator-0-client.crt")] == (
        "client-certificate"
    )
    assert files[str(provider_dir / "provider-garm-configurator-0-client.key")] == "client-key"
    assert files[str(provider_dir / "provider-garm-configurator-0-server.crt")] == (
        "server-certificate"
    )


def test_build_lxd_provider_without_server_certificate_uses_system_trust(monkeypatch, tmp_path):
    """arrange: An LXD provider omits the optional server certificate.

    act: Build the provider files.
    assert: No server certificate file or field is written, so the provider falls back to the
        system trust store for a publicly signed certificate.
    """
    provider_dir = tmp_path / "provider"
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)
    provider = {**_LXD_PROVIDER, "lxd_server_certificate": ""}

    _, files = garm_entrypoint._build_provider_files(
        {"GARM_PROVIDERS_JSON": json.dumps([provider])}
    )

    config_path = provider_dir / "provider-garm-configurator-0.toml"
    config = tomllib.loads(files[str(config_path)])
    assert "tls_server_certificate" not in config
    assert str(provider_dir / "provider-garm-configurator-0-server.crt") not in files


def test_main_removes_stale_provider_certificate_files(monkeypatch, tmp_path):
    """arrange: The provider directory holds certificate files from a previous provider.

    act: Run main with an LXD provider.
    assert: The stale certificate files are removed and the current ones are written.
    """
    config_path = tmp_path / "config.toml"
    provider_dir = tmp_path / "provider"
    provider_dir.mkdir()
    stale_certificate = provider_dir / "provider-old-client.crt"
    stale_key = provider_dir / "provider-old-client.key"
    stale_certificate.write_text("old")
    stale_key.write_text("old")
    monkeypatch.setattr(garm_entrypoint, "GARM_CONFIG_PATH", config_path)
    monkeypatch.setattr(garm_entrypoint, "GARM_PROVIDER_CONFIG_DIR", provider_dir)
    env = {
        "POSTGRESQL_DB_HOSTNAME": "db",
        "POSTGRESQL_DB_USERNAME": "u",
        "POSTGRESQL_DB_PASSWORD": "p",
        "GARM_JWT_SECRET": "j",
        "GARM_PASSPHRASE": "d" * 32,
        "GARM_PROVIDERS_JSON": json.dumps([_LXD_PROVIDER]),
    }

    with (
        patch("garm_entrypoint.os.execvp"),
        patch("garm_entrypoint.os.chmod"),
        patch.dict(os.environ, env, clear=True),
    ):
        garm_entrypoint.main()

    assert not stale_certificate.exists()
    assert not stale_key.exists()
    assert (provider_dir / "provider-garm-configurator-0-client.crt").read_text() == (
        "client-certificate"
    )
    assert (provider_dir / "provider-garm-configurator-0-client.key").read_text() == "client-key"


def test_unknown_provider_type_is_rejected():
    """arrange: A provider names a provider type GARM cannot run.

    act: Build the provider configuration.
    assert: The unknown type is rejected before any config file path is chosen.
    """
    provider = {"unit_name": "garm-configurator-0", "provider_type": "aws"}

    with pytest.raises(garm_entrypoint.InvalidConfigurationError, match="Invalid provider type"):
        garm_entrypoint._build_provider_files({"GARM_PROVIDERS_JSON": json.dumps([provider])})


def test_lxd_provider_missing_required_field_is_rejected():
    """arrange: An LXD provider omits its client key.

    act: Build the provider configuration.
    assert: The missing LXD-specific field is named, rather than the OpenStack fields the
        provider does not use.
    """
    provider = {**_LXD_PROVIDER}
    del provider["lxd_client_key"]

    with pytest.raises(garm_entrypoint.InvalidConfigurationError, match="lxd_client_key"):
        garm_entrypoint._build_provider_files({"GARM_PROVIDERS_JSON": json.dumps([provider])})
