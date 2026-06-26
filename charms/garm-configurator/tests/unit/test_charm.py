# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmConfiguratorCharm."""

import json

import ops
import pytest
from scenario import Context, Relation, Secret, State

from charm import GarmConfiguratorCharm


def _make_secret():
    return Secret(tracked_content={"value": "s3cr3t"})


def _make_private_key_secret():
    return Secret(tracked_content={"value": "random-secret"})


def _make_garm_configurator_relation():
    return Relation(endpoint="garm-configurator")


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
        "github-app-id": "99999",
        "github-app-installation-id": "67890",
        "github-app-private-key": private_key_secret.id,
        "name": "my-scaleset",
        "flavor": "m1.large",
        "os-arch": "amd64",
        "min-idle-runner": 0,
        "max-runner": 5,
        "repo": "myorg/myrepo",
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
            {"github-app-id": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: github-app-id",
            id="missing-github-app-id",
        ),
        pytest.param(
            {"github-app-id": "not-a-number"},
            "github-app-id must be numeric",
            id="non-numeric-github-app-id",
        ),
        pytest.param(
            {"github-app-installation-id": _MISSING_CONFIG_SENTINEL},
            "Missing required configuration: github-app-installation-id",
            id="missing-github-app-installation-id",
        ),
        pytest.param(
            {"github-app-installation-id": "not-a-number"},
            "github-app-installation-id must be numeric",
            id="non-numeric-github-app-installation-id",
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
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "abc-image-uuid"}})
    state = State(config=config, secrets=[secret, pk_secret], relations=[image_relation])
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
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "abc-image-uuid"}})
    state = State(config=config, secrets=[secret, pk_secret], relations=[image_relation])
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == ops.ActiveStatus("Ready")


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
    secret = Secret(
        tracked_content={"value": "old-password"}, latest_content={"value": "new-password"}
    )
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


def test_garm_configurator_relation_data_reflects_charm_state():
    """
    arrange: Valid config and an active garm-configurator relation.
    act: Run config-changed.
    assert: The charm writes all expected scaleset fields to local unit relation data.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    config["labels"] = "self-hosted,linux"
    config["pre-install-scripts"] = "echo hello"
    garm_relation = _make_garm_configurator_relation()
    state = State(
        config=config,
        secrets=[secret, pk_secret],
        relations=[garm_relation],
    )

    out = ctx.run(ctx.on.config_changed(), state)

    rel_out = out.get_relation(garm_relation.id)
    expected_relation_data = {
        "name": "my-scaleset",
        "provider_name": "garm-configurator-0",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "min_idle_runner": "0",
        "max_runner": "5",
        "labels": "self-hosted,linux",
        "runner_group": "Default",
        "pre_install_scripts": '{"pre_install.sh": "echo hello"}',
        "repo": "myorg/myrepo",
    }
    for key, value in expected_relation_data.items():
        assert rel_out.local_unit_data[key] == value


def test_garm_configurator_no_error_when_no_image_relation():
    """
    arrange: Valid config with no image builder relation.
    act: Run config-changed.
    assert: Status is waiting for image builder relation.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    state = State(config=_valid_config(secret, pk_secret), secrets=[secret, pk_secret])

    out = ctx.run(ctx.on.config_changed(), state)

    assert out.unit_status == ops.WaitingStatus("Waiting for image builder relation")


def test_reconcile_writes_full_config_to_garm_relation():
    """
    arrange: All configs valid, image relation has a UUID, garm relation is joined.
    act: config-changed fires (holistic reconcile).
    assert: The full config payload (provider, github, scaleset, image_id) is written
        to the garm-configurator relation's local unit data.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "abc-image-uuid"}})
    garm_relation = Relation(endpoint="garm-configurator")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_relation],
        leader=True,
    )
    out = ctx.run(ctx.on.config_changed(), state)
    garm_out = out.get_relation(garm_relation.id)

    # Provider config
    assert garm_out.local_unit_data["openstack_auth_url"] == (
        "https://keystone.example.com:5000/v3"
    )
    assert garm_out.local_unit_data["openstack_username"] == "admin"
    assert "openstack_password" not in garm_out.local_unit_data
    assert "openstack_password_secret_uri" in garm_out.local_unit_data
    assert garm_out.local_unit_data["openstack_project_name"] == "myproject"
    assert garm_out.local_unit_data["openstack_user_domain_name"] == "Default"
    assert garm_out.local_unit_data["openstack_project_domain_name"] == "Default"
    assert garm_out.local_unit_data["openstack_region_name"] == "RegionOne"
    assert garm_out.local_unit_data["openstack_network"] == "external-net"

    # GitHub config
    assert garm_out.local_unit_data["github_app_id"] == "99999"
    assert garm_out.local_unit_data["github_installation_id"] == "67890"
    assert "github_private_key" not in garm_out.local_unit_data
    assert "github_private_key_secret_uri" in garm_out.local_unit_data

    # Scaleset config
    assert garm_out.local_unit_data["name"] == "my-scaleset"
    assert garm_out.local_unit_data["flavor"] == "m1.large"
    assert garm_out.local_unit_data["os_arch"] == "amd64"
    assert garm_out.local_unit_data["min_idle_runner"] == "0"
    assert garm_out.local_unit_data["max_runner"] == "5"
    assert garm_out.local_unit_data["repo"] == "myorg/myrepo"
    assert garm_out.local_unit_data["runner_group"] == "Default"
    assert "org" not in garm_out.local_unit_data

    # Image UUID
    assert garm_out.local_unit_data["image_id"] == "abc-image-uuid"


def test_reconcile_does_not_write_garm_data_without_image_uuid():
    """
    arrange: All configs valid, garm relation joined, but image relation has NO UUID.
    act: config-changed fires.
    assert: Basic scaleset fields are written but secret-dependent fields
        (openstack credentials, github credentials) are not, since secrets
        are only provisioned once the image UUID is available.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image")  # No remote units data
    garm_relation = Relation(endpoint="garm-configurator")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_relation],
    )
    out = ctx.run(ctx.on.config_changed(), state)
    garm_out = out.get_relation(garm_relation.id)
    assert garm_out.local_unit_data["name"] == "my-scaleset"
    # image_id is empty string when no UUID yet; ops-scenario omits empty strings
    assert "image_id" not in garm_out.local_unit_data
    assert "github_app_id" not in garm_out.local_unit_data
    assert "openstack_auth_url" not in garm_out.local_unit_data


def test_reconcile_writes_garm_data_on_relation_joined():
    """
    arrange: All configs valid, image has UUID, garm relation just joined.
    act: relation_joined fires.
    assert: Config payload is written to the garm relation's local unit data.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "abc-image-uuid"}})
    garm_relation = Relation(endpoint="garm-configurator")
    state = State(
        config=_valid_config(secret, pk_secret),
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_relation],
        leader=True,
    )
    out = ctx.run(ctx.on.relation_joined(garm_relation), state)
    garm_out = out.get_relation(garm_relation.id)
    assert garm_out.local_unit_data["image_id"] == "abc-image-uuid"
    assert garm_out.local_unit_data["name"] == "my-scaleset"
    assert garm_out.local_unit_data["github_app_id"] == "99999"
    assert garm_out.local_unit_data["openstack_username"] == "admin"


def test_reconcile_writes_optional_scaleset_fields_to_garm_relation():
    """
    arrange: Config uses org instead of repo, with runner_group and pre_install_scripts.
        Image UUID is present, garm relation is joined.
    act: config-changed fires.
    assert: org, runner_group, and pre_install_scripts are present in the
        garm relation data. repo is absent.
    """
    ctx = Context(GarmConfiguratorCharm)
    secret = _make_secret()
    pk_secret = _make_private_key_secret()
    config = _valid_config(secret, pk_secret)
    del config["repo"]
    config["org"] = "myorg"
    config["runner-group"] = "my-group"
    config["pre-install-scripts"] = '{"setup.sh": "#!/bin/bash\\necho hello"}'
    image_relation = Relation(endpoint="image", remote_units_data={0: {"id": "abc-image-uuid"}})
    garm_relation = Relation(endpoint="garm-configurator")
    state = State(
        config=config,
        secrets=[secret, pk_secret],
        relations=[image_relation, garm_relation],
        leader=True,
    )
    out = ctx.run(ctx.on.config_changed(), state)
    garm_out = out.get_relation(garm_relation.id)

    assert garm_out.local_unit_data["org"] == "myorg"
    assert garm_out.local_unit_data["runner_group"] == "my-group"
    assert garm_out.local_unit_data["pre_install_scripts"] == json.dumps(
        {"pre_install.sh": '{"setup.sh": "#!/bin/bash\\necho hello"}'}
    )
    assert "repo" not in garm_out.local_unit_data
