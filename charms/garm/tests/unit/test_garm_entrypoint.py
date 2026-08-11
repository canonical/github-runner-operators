#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the GARM entrypoint script."""

import logging
import os
from unittest.mock import patch

import pytest

import garm_entrypoint


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
        "/usr/local/bin/garm", ["garm", "-config", str(config_path)]
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
        "/usr/local/bin/garm", ["garm", "-config", str(config_path)]
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
        "/usr/local/bin/garm", ["garm", "-config", str(config_path)]
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
