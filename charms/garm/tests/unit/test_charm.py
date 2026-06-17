# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import string
from unittest.mock import MagicMock, patch

import ops
import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from garm_api import GarmConnectionError

from charm import (
    GARM_ADMIN_CREDENTIALS_LABEL,
    GARM_SECRETS_LABEL,
    GarmCharm,
    _generate_admin_password,
    _generate_garm_secrets,
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


def _render(**overrides) -> dict:
    """Helper: render TOML with defaults, return parsed dict."""
    kwargs = {
        "listen_port": 8080,
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
        ("apiserver", "bind", "0.0.0.0", {}),
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
