# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmConfiguratorCharm."""

import ops
from scenario import Context, Secret, State

from charm import GarmConfiguratorCharm


def _make_secret():
    return Secret(tracked_content={"value": "s3cr3t"})


def _make_private_key_secret():
    return Secret(tracked_content={"value": "random-secret"})


def _valid_config(secret: Secret, private_key_secret: Secret) -> dict:
    return {
        "openstack-auth-url": "https://keystone.example.com:5000/v3",
        "openstack-username": "admin",
        "openstack-password": secret.id,
        "openstack-project-name": "myproject",
        "openstack-user-domain-name": "Default",
        "openstack-project-domain-name": "Default",
        "openstack-region-name": "RegionOne",
        "openstack-interface": "public",
        "openstack-identity-api-version": 3,
        "openstack-network": "external-net",
        "github-app-client-id": "12345",
        "github-app-installation-id": "67890",
        "github-app-private-key": private_key_secret.id,
    }


def test_charm_active_with_valid_config():
    """
    arrange: All configs are valid.
    act: Run config-changed.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    state = State(config=_valid_config(secret, pk_secret), secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_blocked_missing_auth_url():
    """
    arrange: openstack-auth-url is missing.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["openstack-auth-url"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: openstack-auth-url"
    )


def test_charm_blocked_empty_username():
    """
    arrange: openstack-username is empty string.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-username"] = ""
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: openstack-username"
    )


def test_charm_blocked_invalid_auth_url():
    """
    arrange: openstack-auth-url does not start with http:// or https://.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-auth-url"] = "ftp://invalid.example.com"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "openstack-auth-url must start with http:// or https://"
    )


def test_charm_blocked_invalid_interface():
    """
    arrange: openstack-interface is not one of public, internal, admin.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-interface"] = "private"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "openstack-interface must be one of: public, internal, admin"
    )


def test_charm_blocked_missing_identity_api_version():
    """
    arrange: openstack-identity-api-version is not set.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["openstack-identity-api-version"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: openstack-identity-api-version"
    )


def test_charm_blocked_missing_password_secret():
    """
    arrange: openstack-password config is not set.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["openstack-password"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: openstack-password"
    )


def test_charm_blocked_password_secret_missing_value_key():
    """
    arrange: openstack-password secret exists but lacks 'value' key.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = Secret(tracked_content={"wrong-key": "data"})
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "openstack-password secret is invalid or missing 'value' key"
    )


def test_charm_blocked_password_secret_not_found():
    """
    arrange: openstack-password references a secret that doesn't exist in state.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    state = State(config=config, secrets=[pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "openstack-password secret is invalid or missing 'value' key"
    )


def test_charm_active_with_http_auth_url():
    """
    arrange: openstack-auth-url uses http:// (not https://).
    act: Run config-changed.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-auth-url"] = "http://keystone.local:5000/v3"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_active_with_internal_interface():
    """
    arrange: openstack-interface is 'internal'.
    act: Run config-changed.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-interface"] = "internal"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_active_with_admin_interface():
    """
    arrange: openstack-interface is 'admin'.
    act: Run config-changed.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-interface"] = "admin"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_blocked_whitespace_only_config():
    """
    arrange: openstack-network is whitespace only.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-network"] = "   "
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: openstack-network"
    )


def test_charm_collect_unit_status_blocked_after_invalid_config():
    """
    arrange: Invalid config causes BlockedStatus on config-changed.
    act: Run collect-unit-status after config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["openstack-password"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: openstack-password"
    )


def test_charm_blocked_missing_github_app_client_id():
    """
    arrange: github-app-client-id is missing.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["github-app-client-id"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: github-app-client-id"
    )


def test_charm_blocked_missing_github_app_installation_id():
    """
    arrange: github-app-installation-id is missing.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["github-app-installation-id"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: github-app-installation-id"
    )


def test_charm_blocked_missing_github_app_private_key():
    """
    arrange: github-app-private-key config is not set.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["github-app-private-key"]
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "Missing required configuration: github-app-private-key"
    )


def test_charm_blocked_github_app_private_key_secret_missing_value_key():
    """
    arrange: github-app-private-key secret exists but lacks 'value' key.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    bad_pk_secret = Secret(tracked_content={"wrong-key": "data"})
    config = _valid_config(secret, bad_pk_secret)
    state = State(config=config, secrets=[secret, bad_pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "github-app-private-key secret is invalid or missing 'value' key"
    )


def test_charm_blocked_github_app_private_key_secret_not_found():
    """
    arrange: github-app-private-key references a secret not in state.
    act: Run config-changed.
    assert: Unit status is Blocked.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    state = State(config=config, secrets=[secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(
        "github-app-private-key secret is invalid or missing 'value' key"
    )
