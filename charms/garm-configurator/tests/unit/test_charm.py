# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmConfiguratorCharm."""

import ops
import pytest
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
        "openstack-network": "external-net",
        "github-app-client-id": "12345",
        "github-app-installation-id": "67890",
        "github-app-private-key": private_key_secret.id,
        "name": "my-scaleset",
        "flavor": "m1.large",
        "os-arch": "amd64",
        "min-idle-runner": 0,
        "max-runner": 5,
        "repo": "myorg/myrepo",
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


# Represents a missing config value in parameterized tests below
_MISSING_CONFIG_SENTINEL = object()


@pytest.mark.parametrize(
    "config_mutations, expected_message",
    [
        pytest.param(
            {"openstack-auth-url": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: openstack-auth-url",
            id="missing-auth-url",
        ),
        pytest.param(
            {"openstack-username": ""},
            "Missing required configuration: openstack-username",
            id="empty-username",
        ),
        pytest.param(
            {"openstack-password": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: openstack-password",
            id="missing-password",
        ),
        pytest.param(
            {"openstack-network": "   "},
            "Missing required configuration: openstack-network",
            id="whitespace-only-network",
        ),
        pytest.param(
            {"github-app-client-id": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: github-app-client-id",
            id="missing-github-app-client-id",
        ),
        pytest.param(
            {"github-app-installation-id": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: github-app-installation-id",
            id="missing-github-app-installation-id",
        ),
        pytest.param(
            {"github-app-private-key": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: github-app-private-key",
            id="missing-github-app-private-key",
        ),
        pytest.param(
            {"name": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: name",
            id="missing-name",
        ),
        pytest.param(
            {"flavor": ""},
            "Missing required configuration: flavor",
            id="empty-flavor",
        ),
        pytest.param(
            {"os-arch": "   "},
            "Missing required configuration: os-arch",
            id="whitespace-only-os-arch",
        ),
        pytest.param(
            {"openstack-auth-url": "ftp://invalid.example.com"},
            "openstack-auth-url must start with http:// or https://",
            id="invalid-auth-url",
        ),
        pytest.param(
            {"min-idle-runner": -1},
            "min-idle-runner must be non-negative",
            id="negative-min-idle-runner",
        ),
        pytest.param(
            {"max-runner": -5},
            "max-runner must be non-negative",
            id="negative-max-runner",
        ),
        pytest.param(
            {"min-idle-runner": 5, "max-runner": 3},
            "max-runner must be greater than or equal to min-idle-runner",
            id="max-runner-less-than-min-idle-runner",
        ),
        pytest.param(
            {"repo": _MISSING_CONFIG_SENTINEL},
            "At least one of repo or org must be provided",
            id="neither-repo-nor-org",
        ),
        pytest.param(
            {"org": "myorg"},
            "repo and org are mutually exclusive",
            id="repo-and-org-both-set",
        ),
    ],
)
def test_charm_blocked_invalid_config(config_mutations: dict, expected_message: str):
    """
    arrange: Config is invalid (missing, empty, or has an invalid value).
    act: Run config-changed.
    assert: Unit status is Blocked with the expected message.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    for key, value in config_mutations.items():
        if value is _MISSING_CONFIG_SENTINEL:
            del config[key]
        else:
            config[key] = value
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(expected_message)


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


def test_charm_active_with_org_and_runner_group():
    """
    arrange: org and runner-group are set (no repo).
    act: Run config-changed.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["repo"]
    config["org"] = "myorg"
    config["runner-group"] = "my-group"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_active_with_org_only():
    """
    arrange: Only org is set (no repo, no runner-group).
    act: Run config-changed.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["repo"]
    config["org"] = "myorg"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")
