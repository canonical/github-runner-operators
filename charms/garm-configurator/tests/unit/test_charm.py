# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmConfiguratorCharm."""

import ops
import pytest
from scenario import Context, Relation, Secret, State

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
    }


def test_charm_waiting_with_valid_config_no_relation():
    """
    arrange: All configs are valid but no image builder relation.
    act: Run config-changed.
    assert: Unit status is Waiting — image builder relation is required.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    state = State(config=_valid_config(secret, pk_secret), secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.WaitingStatus("Waiting for image builder relation")


# Represents a missing config value in parameterized tests below
_MISSING_CONFIG_SENTINEL = object()


@pytest.mark.parametrize(
    "config_key, override_value",
    [
        pytest.param("openstack-auth-url", _MISSING_CONFIG_SENTINEL, id="missing-auth-url"),
        pytest.param("openstack-username", "", id="empty-username"),
        pytest.param("openstack-password", _MISSING_CONFIG_SENTINEL, id="missing-password"),
        pytest.param("openstack-network", "   ", id="whitespace-only-network"),
        pytest.param(
            "github-app-client-id", _MISSING_CONFIG_SENTINEL, id="missing-github-app-client-id"
        ),
        pytest.param(
            "github-app-installation-id",
            _MISSING_CONFIG_SENTINEL,
            id="missing-github-app-installation-id",
        ),
        pytest.param(
            "github-app-private-key",
            _MISSING_CONFIG_SENTINEL,
            id="missing-github-app-private-key",
        ),
    ],
)
def test_charm_blocked_missing_or_empty_config(config_key: str, override_value: object):
    """
    arrange: A required config key is missing or empty/whitespace.
    act: Run config-changed.
    assert: Unit status is Blocked with the expected message.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    if override_value is _MISSING_CONFIG_SENTINEL:
        del config[config_key]
    else:
        config[config_key] = override_value
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.BlockedStatus(f"Missing required configuration: {config_key}")


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


def test_charm_not_blocked_with_http_auth_url():
    """
    arrange: openstack-auth-url uses http:// (not https://).
    act: Run config-changed.
    assert: Unit status is not Blocked — http:// is a valid scheme.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["openstack-auth-url"] = "http://keystone.local:5000/v3"
    state = State(config=config, secrets=[secret, pk_secret])
    out = ctx.run(ctx.on.config_changed(), state)
    assert not isinstance(out.unit_status, ops.BlockedStatus)


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


# ---------------------------------------------------------------------------
# Image relation — credential forwarding
# ---------------------------------------------------------------------------


def test_reconcile_writes_openstack_credentials_to_image_relation():
    """
    arrange: Valid config and an image relation with no existing data.
    act: relation_joined fires (holistic reconcile).
    assert: All six OpenStack credential fields are written to local unit data.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.relation_joined(image_relation), state)
    rel_out = out.get_relation(image_relation.id)
    assert rel_out.local_unit_data["auth_url"] == "https://keystone.example.com:5000/v3"
    assert rel_out.local_unit_data["username"] == "admin"
    assert rel_out.local_unit_data["password"] == "s3cr3t"
    assert rel_out.local_unit_data["project_name"] == "myproject"
    assert rel_out.local_unit_data["user_domain_name"] == "Default"
    assert rel_out.local_unit_data["project_domain_name"] == "Default"


def test_reconcile_writes_credentials_on_secret_changed():
    """
    arrange: Valid config, existing image relation, OpenStack password secret has a new revision.
    act: secret_changed fires for the password secret.
    assert: The rotated password (latest revision) is pushed to the relation databag.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = Secret(tracked_content={"value": "old-password"}, latest_content={"value": "new-password"})
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.secret_changed(secret), state)
    rel_out = out.get_relation(image_relation.id)
    assert rel_out.local_unit_data["password"] == "new-password"


def test_reconcile_writes_credentials_on_config_changed_with_existing_relation():
    """
    arrange: Valid config and an existing image relation.
    act: config-changed fires (holistic reconcile).
    assert: Credentials are written to the relation even outside relation_joined.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)
    rel_out = out.get_relation(image_relation.id)
    assert rel_out.local_unit_data["auth_url"] == "https://keystone.example.com:5000/v3"
    assert rel_out.local_unit_data["project_name"] == "myproject"


def test_reconcile_does_not_write_credentials_when_config_invalid():
    """
    arrange: Missing openstack-auth-url and an image relation joined.
    act: relation_joined fires.
    assert: Local unit data remains empty (no credentials forwarded).
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["openstack-auth-url"]
    image_relation = Relation(endpoint="image")
    state = State(
        config=config,
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.relation_joined(image_relation), state)
    rel_out = out.get_relation(image_relation.id)
    assert "auth_url" not in rel_out.local_unit_data


# ---------------------------------------------------------------------------
# Image relation — unit status
# ---------------------------------------------------------------------------


def test_status_waiting_when_image_relation_has_no_uuid():
    """
    arrange: Valid config, image relation joined, but provider has not set an image UUID yet.
    act: relation_changed fires (no UUID in remote data).
    assert: Unit status is Waiting.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.relation_changed(image_relation), state)
    assert out.unit_status == ops.WaitingStatus("Waiting for image UUID from image builder")


def test_status_active_when_image_uuid_is_present():
    """
    arrange: Valid config, image relation joined, provider has set a UUID.
    act: relation_changed fires with UUID in remote data.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "abc-image-uuid"}})
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.relation_changed(image_relation), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_status_waiting_when_no_image_relation():
    """
    arrange: Valid config, no image relation.
    act: config_changed fires.
    assert: Unit status is Waiting — the image builder relation is required.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
    )
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.WaitingStatus("Waiting for image builder relation")


def test_status_waiting_on_relation_broken():
    """
    arrange: Valid config and the image relation being torn down.
    act: relation_broken fires.
    assert: Unit status is Waiting — ops excludes the breaking relation from model.relations,
        so the charm correctly reflects that it has no image builder connected.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation],
    )
    out = ctx.run(ctx.on.relation_broken(image_relation), state)
    assert out.unit_status == ops.WaitingStatus("Waiting for image builder relation")


