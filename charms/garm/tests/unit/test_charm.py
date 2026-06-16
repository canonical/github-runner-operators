# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmCharm."""

import string
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from charm import GARM_SECRETS_LABEL, GarmCharm, _generate_garm_secrets, render_garm_toml

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


def test_generate_garm_secrets_includes_admin_username():
    """Generated secrets include the fixed admin username."""
    result = _generate_garm_secrets()
    assert result["admin-username"] == "admin"


def test_generate_garm_secrets_includes_admin_password():
    """Generated secrets include a strong admin password with the expected wrapper."""
    result = _generate_garm_secrets()
    password = result["admin-password"]
    assert password.startswith("Admin-")
    assert password.endswith("-Gx1!")


def test_admin_password_format_is_strong():
    """Generated admin passwords satisfy the expected strength constraints."""
    for _ in range(5):
        password = _generate_garm_secrets()["admin-password"]
        assert len(password) >= 12
        assert any(char.isupper() for char in password)
        assert any(char.islower() for char in password)
        assert any(char.isdigit() for char in password)
        assert any(not char.isalnum() for char in password)


def test_admin_username_is_always_admin():
    """Generated admin username remains stable across calls."""
    for _ in range(5):
        assert _generate_garm_secrets()["admin-username"] == "admin"


def test_generate_garm_secrets_does_not_overwrite_existing():
    """Existing garm-secrets are preserved when the charm ensures secrets."""
    charm = object.__new__(GarmCharm)
    mock_unit = MagicMock()
    mock_unit.is_leader.return_value = True
    existing_secret = MagicMock()
    existing_secret.get_content.return_value = {
        "jwt-secret": "existing-jwt",
        "db-passphrase": "existing-passphrase",
        "admin-username": "admin",
        "admin-password": "Admin-deadbeefcafebabe-Gx1!",
    }
    mock_model = MagicMock()
    mock_model.get_secret.return_value = existing_secret
    mock_app = MagicMock()

    with (
        patch.object(GarmCharm, "unit", new_callable=PropertyMock, return_value=mock_unit),
        patch.object(GarmCharm, "model", new_callable=PropertyMock, return_value=mock_model),
        patch.object(GarmCharm, "app", new_callable=PropertyMock, return_value=mock_app),
    ):
        charm._ensure_secrets()

    mock_model.get_secret.assert_called_once_with(label=GARM_SECRETS_LABEL)
    mock_app.add_secret.assert_not_called()
    existing_secret.set_content.assert_not_called()


def test_ensure_secrets_backfills_missing_admin_credentials():
    """Existing secrets gain admin credentials without changing current values."""
    charm = object.__new__(GarmCharm)
    mock_unit = MagicMock()
    mock_unit.is_leader.return_value = True
    existing_secret = MagicMock()
    existing_secret.get_content.return_value = {
        "jwt-secret": "existing-jwt",
        "db-passphrase": "existing-passphrase",
    }
    mock_model = MagicMock()
    mock_model.get_secret.return_value = existing_secret
    mock_app = MagicMock()

    with (
        patch.object(GarmCharm, "unit", new_callable=PropertyMock, return_value=mock_unit),
        patch.object(GarmCharm, "model", new_callable=PropertyMock, return_value=mock_model),
        patch.object(GarmCharm, "app", new_callable=PropertyMock, return_value=mock_app),
    ):
        charm._ensure_secrets()

    existing_secret.set_content.assert_called_once()
    updated = existing_secret.set_content.call_args[0][0]
    assert updated["jwt-secret"] == "existing-jwt"
    assert updated["db-passphrase"] == "existing-passphrase"
    assert updated["admin-username"] == "admin"
    assert updated["admin-password"].startswith("Admin-")
    assert updated["admin-password"].endswith("-Gx1!")


def test_admin_password_is_unique_across_calls():
    """Separate generated secret payloads use different admin passwords."""
    first = _generate_garm_secrets()
    second = _generate_garm_secrets()
    assert first["admin-password"] != second["admin-password"]


def test_reconcile_scalesets_skips_when_no_secrets():
    """Scaleset reconciliation exits early when GARM secrets are unavailable."""
    charm = object.__new__(GarmCharm)
    charm._maybe_first_run = MagicMock()
    charm._get_garm_secrets = MagicMock(return_value=None)

    with patch("charm.GarmClient") as mock_client:
        charm._reconcile_scalesets()

    mock_client.assert_not_called()


def test_reconcile_scalesets_skips_restart():
    """Scaleset reconciliation must not restart the workload."""
    charm = object.__new__(GarmCharm)
    charm._maybe_first_run = MagicMock()
    secret = MagicMock()
    secret.get_content.return_value = {
        "admin-username": "admin",
        "admin-password": "Admin-deadbeefcafebabe-Gx1!",
    }
    charm._get_garm_secrets = MagicMock(return_value=secret)
    charm._get_garm_url = MagicMock(return_value="http://garm")
    charm._build_desired_scalesets = MagicMock(return_value=[])
    charm.restart = MagicMock()
    charm._restart_service = MagicMock()

    with patch("charm.GarmClient") as mock_client_cls, patch("charm.ScalesetReconciler") as mock_reconciler_cls:
        mock_client = mock_client_cls.return_value
        mock_client.login.return_value = "token"

        charm._reconcile_scalesets()

    mock_client.login.assert_called_once_with("admin", "Admin-deadbeefcafebabe-Gx1!")
    mock_reconciler_cls.return_value.reconcile.assert_called_once_with([])
    charm.restart.assert_not_called()
    charm._restart_service.assert_not_called()


def test_maybe_first_run_registers_admin_from_secret():
    """The leader registers GARM's admin using the garm-secrets credentials."""
    charm = object.__new__(GarmCharm)
    secret = MagicMock()
    secret.get_content.return_value = {
        "admin-username": "admin",
        "admin-password": "Admin-deadbeefcafebabe-Gx1!",
    }
    charm._get_garm_secrets = MagicMock(return_value=secret)
    charm._get_garm_url = MagicMock(return_value="http://127.0.0.1:8080")

    with (
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
        patch("charm.GarmClient") as mock_client_cls,
    ):
        mock_unit.return_value.is_leader.return_value = True
        charm._maybe_first_run()

    mock_client_cls.return_value.first_run.assert_called_once_with(
        "admin", "Admin-deadbeefcafebabe-Gx1!", "admin@garm.local", "GARM Admin"
    )


def test_maybe_first_run_skips_when_not_leader():
    """Non-leader units do not attempt GARM first-run."""
    charm = object.__new__(GarmCharm)

    with (
        patch.object(GarmCharm, "unit", new_callable=PropertyMock) as mock_unit,
        patch("charm.GarmClient") as mock_client_cls,
    ):
        mock_unit.return_value.is_leader.return_value = False
        charm._maybe_first_run()

    mock_client_cls.assert_not_called()
