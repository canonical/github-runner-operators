#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GARM entrypoint configuration boundary."""

import os
from unittest.mock import patch

import pytest

import garm_entrypoint
from charm import _generate_admin_password, _generate_garm_secrets

_ENV = {
    "POSTGRESQL_DB_HOSTNAME": "10.0.0.5",
    "POSTGRESQL_DB_USERNAME": "garm",
    "POSTGRESQL_DB_PASSWORD": "pass",
    "GARM_JWT_SECRET": "jwt",
    "GARM_PASSPHRASE": "a" * 32,
}


def test_render_garm_config_postgresql_and_provider_data():
    """arrange: The entrypoint environment contains PostgreSQL and OpenStack provider data.

    act: Render the GARM configuration.
    assert: The entrypoint emits the database and provider configuration consumed by GARM.
    """
    env = {
        **_ENV,
        "POSTGRESQL_DB_PORT": "5433",
        "POSTGRESQL_DB_NAME": "garmdb",
        "GARM_PROVIDERS_JSON": (
            '[{"unit_name":"provider-0","auth_url":"https://keystone",'
            '"username":"u","password":"p","project_name":"project",'
            '"user_domain_name":"Default","project_domain_name":"Default",'
            '"region_name":"RegionOne","network":"private"}]'
        ),
    }

    with patch.dict(os.environ, env, clear=True):
        config = garm_entrypoint.render_garm_config(env)

    assert 'hostname = "10.0.0.5"' in config
    assert "port = 5433" in config
    assert 'database = "garmdb"' in config
    assert 'name = "provider-0"' in config
    assert 'config_file = "/etc/garm/provider-provider-0.toml"' in config


def test_render_garm_config_uses_database_defaults():
    """arrange: Only the required entrypoint environment variables are set.

    act: Render the GARM configuration.
    assert: The standard PostgreSQL port and database name are used.
    """
    with patch.dict(os.environ, _ENV, clear=True):
        config = garm_entrypoint.render_garm_config(_ENV)

    assert "port = 5432" in config
    assert 'database = "garm"' in config


def test_provider_unit_name_cannot_escape_config_directory():
    """arrange: Provider data contains a path traversal unit name.

    act: Build provider configuration files.
    assert: The entrypoint rejects the name before creating an escaped path.
    """
    with pytest.raises(
        garm_entrypoint.InvalidConfigurationError, match="Invalid provider unit name"
    ):
        garm_entrypoint._build_provider_files({"GARM_PROVIDERS_JSON": '[{"unit_name":"../x"}]'})


def test_proxy_environment_is_forwarded_to_external_provider():
    """arrange: Both lower- and upper-case proxy variables are available.

    act: Build provider configuration.
    assert: The external provider receives the configured proxy variable names.
    """
    env = {
        "GARM_PROVIDERS_JSON": '[{"unit_name":"provider-0","network":"private",'
        '"auth_url":"url","username":"u","password":"p",'
        '"project_name":"project","user_domain_name":"Default",'
        '"project_domain_name":"Default","region_name":"RegionOne"}]',
        "http_proxy": "http://proxy.example",
        "HTTP_PROXY": "http://proxy.example",
    }

    entries, _ = garm_entrypoint._build_provider_files(env)

    assert entries[0]["external"]["environment_variables"] == ["HTTP_PROXY", "http_proxy"]


def test_generate_garm_secrets_returns_required_values():
    """arrange: No existing GARM secrets are supplied.

    act: Generate GARM secrets.
    assert: JWT and database passphrase values are returned in the expected shapes.
    """
    secrets = _generate_garm_secrets()

    assert len(secrets["jwt-secret"]) == 64
    assert len(secrets["db-passphrase"]) == 32


def test_generate_admin_password_meets_garm_policy():
    """arrange: GARM needs a new administrator password.

    act: Generate the password.
    assert: The password includes uppercase, lowercase, digit, and symbol characters.
    """
    password = _generate_admin_password()

    assert len(password) == 20
    assert any(char.isupper() for char in password)
    assert any(char.islower() for char in password)
    assert any(char.isdigit() for char in password)
    assert any(char in "!@#$%-_=+" for char in password)
