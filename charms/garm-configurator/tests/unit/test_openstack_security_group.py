# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the OpenStack security group reconciler."""

import typing

import pytest

from charm_state import ProviderConfig, SecurityGroupRule
from openstack_security_group import (
    MAX_STATUS_REASON_LENGTH,
    SecurityGroupReconcileError,
    SecurityGroupReconciler,
    security_group_name,
)

SCALESET_NAME = "my-scaleset"
GROUP_NAME = "garm-my-scaleset"
RULE_ATTRIBUTES = (
    "direction",
    "ethertype",
    "protocol",
    "port_range_min",
    "port_range_max",
    "remote_ip_prefix",
    "remote_group_id",
    "remote_address_group_id",
)


class _FakeRule:
    """A security group rule as the SDK reports it."""

    def __init__(self, **fields):
        for field in RULE_ATTRIBUTES:
            setattr(self, field, fields.get(field))
        # Fields OpenStack assigns, which a diff must ignore.
        self.id = fields.get("id", "rule-id")
        self.description = fields.get("description", "")


class _FakeGroup:
    """A security group as the SDK reports it."""

    def __init__(self, name, gid="sg-1", created_at="2026-01-01T00:00:00Z", rules=()):
        self.id = gid
        self.name = name
        self.created_at = created_at
        self.rules = list(rules)


class _FakeNetwork:
    """The network service of a fake OpenStack connection."""

    def __init__(self, groups=()):
        self.groups = list(groups)
        self.created_groups = []
        self.deleted_groups = []
        self.created_rules = []
        self.deleted_rules = []

    def security_groups(self):
        return self.groups

    def create_security_group(self, name, description):
        group = _FakeGroup(name, gid=f"sg-{name}")
        self.groups.append(group)
        self.created_groups.append(name)
        return group

    def delete_security_group(self, group_id):
        self.deleted_groups.append(group_id)
        self.groups = [group for group in self.groups if group.id != group_id]

    def security_group_rules(self, security_group_id):
        return list(self._group(security_group_id).rules)

    def create_security_group_rule(self, security_group_id, **fields):
        self.created_rules.append(fields)
        rule = _FakeRule(**fields)
        self._group(security_group_id).rules.append(rule)
        return rule

    def delete_security_group_rule(self, rule):
        self.deleted_rules.append(rule.id)
        self._group_by_rule(rule).rules.remove(rule)

    def _group(self, group_id):
        return next(group for group in self.groups if group.id == group_id)

    def _group_by_rule(self, rule):
        return next(group for group in self.groups if rule in group.rules)


class _FakeConnection:
    """A fake OpenStack connection holding one network service."""

    def __init__(self, network):
        self.network = network
        self.closed = False

    def close(self):
        self.closed = True


def _provider_config():
    """Build the OpenStack credentials the reconciler authenticates with."""
    return ProviderConfig(
        auth_url="https://keystone.example.com:5000/v3",
        username="admin",
        password="s3cr3t",
        project_name="myproject",
        user_domain_name="Default",
        project_domain_name="Default",
        region_name="RegionOne",
        network="external-net",
        provider_name="garm-configurator-0",
    )


def _reconciler(network):
    """Build a reconciler over *network*, plus the connection and auth arguments it used."""
    connection = _FakeConnection(network)
    calls: dict[str, typing.Any] = {}

    def connect(**auth_fields):
        calls["auth"] = auth_fields
        return connection

    return SecurityGroupReconciler(_provider_config(), connect=connect), connection, calls


def _rule_fields(
    direction, protocol=None, port_min=None, port_max=None, prefix=None, ethertype="IPv4"
):
    """Build the fields OpenStack creates one rule from."""
    return {
        "direction": direction,
        "ethertype": ethertype,
        "protocol": protocol,
        "port_range_min": port_min,
        "port_range_max": port_max,
        "remote_ip_prefix": prefix,
    }


def _stored_rule(**fields):
    """Build a rule as OpenStack reports it, with the id it assigned."""
    return _FakeRule(id=f"rule-{fields.pop('rule_id', 99)}", **fields)


SSH = SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)
EGRESS_ALL_V4_RULE = SecurityGroupRule(direction="egress", remote_ip_prefix="0.0.0.0/0")
SSH_INGRESS = _rule_fields("ingress", protocol="tcp", port_min=22, port_max=22)
SSH_INGRESS_FROM_SUBNET = _rule_fields(
    "ingress", protocol="tcp", port_min=22, port_max=22, prefix="10.0.0.0/8"
)
EGRESS_ALL_V4 = _rule_fields("egress", prefix="0.0.0.0/0")


def test_security_group_name_is_derived_from_the_scaleset_name():
    """
    arrange: A scaleset name.
    act: Derive the managed security group name.
    assert: The name is prefixed, so it is recognisably charm-managed and stable across
        restarts and upgrades.
    """
    assert security_group_name(SCALESET_NAME) == GROUP_NAME


def test_missing_group_is_created_with_the_configured_rules():
    """
    arrange: A project with no managed security group yet.
    act: Reconcile one ingress rule and one egress rule.
    assert: The group is created holding exactly those rules, because the option is the only
        source of the group's rules.
    """
    network = _FakeNetwork()
    reconciler, _, _ = _reconciler(network)

    group_id = reconciler.reconcile(
        GROUP_NAME,
        [
            SecurityGroupRule(
                direction="ingress",
                protocol="tcp",
                port_min=22,
                port_max=22,
                remote_ip_prefix="10.0.0.0/8",
            ),
            EGRESS_ALL_V4_RULE,
        ],
    )

    assert network.created_groups == [GROUP_NAME]
    assert network.created_rules == [SSH_INGRESS_FROM_SUBNET, EGRESS_ALL_V4]
    assert group_id == f"sg-{GROUP_NAME}"


def test_duplicate_configured_rules_are_created_once():
    """
    arrange: Rules that list the same ingress rule twice.
    act: Reconcile the rules.
    assert: One rule is created, so the group does not carry a duplicate the next reconcile
        would then have to remove.
    """
    network = _FakeNetwork()
    reconciler, _, _ = _reconciler(network)

    reconciler.reconcile(GROUP_NAME, [SSH, SSH, EGRESS_ALL_V4_RULE])

    assert network.created_rules == [SSH_INGRESS, EGRESS_ALL_V4]


def test_existing_group_is_reused_and_its_matching_rules_are_left_alone():
    """
    arrange: A group that already holds the desired rules, with the ids OpenStack assigned.
    act: Reconcile the same rules again.
    assert: The existing group and its rules are kept, so reconciling unchanged configuration
        makes no change at all.
    """
    group = _FakeGroup(
        GROUP_NAME,
        gid="sg-existing",
        rules=[_stored_rule(**SSH_INGRESS), _stored_rule(**EGRESS_ALL_V4)],
    )
    network = _FakeNetwork([group])
    reconciler, _, _ = _reconciler(network)

    group_id = reconciler.reconcile(GROUP_NAME, [SSH, EGRESS_ALL_V4_RULE])

    assert group_id == "sg-existing"
    assert network.created_groups == []
    assert network.created_rules == []
    assert network.deleted_rules == []


def test_rules_no_longer_configured_are_deleted():
    """
    arrange: A group holding a rule the operator has since removed.
    act: Reconcile the remaining rules.
    assert: The stale rule is deleted, so the group matches the option exactly.
    """
    group = _FakeGroup(
        GROUP_NAME,
        rules=[
            _stored_rule(**SSH_INGRESS, rule_id=1),
            _stored_rule(
                **_rule_fields("ingress", protocol="tcp", port_min=8080, port_max=8080), rule_id=2
            ),
        ],
    )
    network = _FakeNetwork([group])
    reconciler, _, _ = _reconciler(network)

    reconciler.reconcile(GROUP_NAME, [SSH, EGRESS_ALL_V4_RULE])

    assert network.deleted_rules == ["rule-2"]
    assert network.created_rules == [EGRESS_ALL_V4]


def test_a_rule_added_by_hand_is_removed():
    """
    arrange: A group holding a rule the operator never configured, such as one added with the
        OpenStack CLI.
    act: Reconcile.
    assert: The rule is removed, because the option is the only source of the group's rules.
    """
    group = _FakeGroup(
        GROUP_NAME,
        rules=[
            _stored_rule(
                **_rule_fields("ingress", protocol="tcp", port_min=3389, port_max=3389), rule_id=7
            )
        ],
    )
    network = _FakeNetwork([group])
    reconciler, _, _ = _reconciler(network)

    reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert network.deleted_rules == ["rule-7"]
    assert network.created_rules == [EGRESS_ALL_V4]


def test_duplicate_groups_keep_the_oldest_and_delete_the_rest():
    """
    arrange: Two groups sharing the managed name, as a race between two configurators leaves.
    act: Reconcile.
    assert: The older group is adopted and the newer one deleted, so the charm converges on one
        group instead of failing, and two configurators racing pick the same survivor.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ]
    )
    reconciler, _, _ = _reconciler(network)

    group_id = reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert group_id == "sg-older"
    assert network.deleted_groups == ["sg-newer"]
    assert network.created_groups == []


def test_a_duplicate_that_cannot_be_deleted_blocks_the_reconcile():
    """
    arrange: Two groups sharing the managed name, and an OpenStack that refuses the delete
        because a port still references the obsolete one.
    act: Reconcile.
    assert: The failure reaches the caller as a reconcile error, so the unit blocks instead of
        silently converging on one of two groups.
    """

    class _RefusesDelete(_FakeNetwork):
        def delete_security_group(self, group_id):
            raise RuntimeError("Security Group sg-newer in use")

    network = _RefusesDelete(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ]
    )
    reconciler, _, _ = _reconciler(network)

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert "in use" in str(exc_info.value)


def test_connection_is_closed_after_a_successful_reconcile():
    """
    arrange: A working connection.
    act: Reconcile.
    assert: The connection is closed, so repeated reconciles do not leak sessions.
    """
    reconciler, connection, _ = _reconciler(_FakeNetwork())

    reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert connection.closed is True


def test_authentication_uses_the_provider_config():
    """
    arrange: The charm state's provider credentials.
    act: Reconcile.
    assert: The SDK is given those credentials, the configured region, and the public endpoint
        interface.
    """
    reconciler, _, calls = _reconciler(_FakeNetwork())

    reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert calls["auth"] == {
        "auth_url": "https://keystone.example.com:5000/v3",
        "username": "admin",
        "password": "s3cr3t",
        "project_name": "myproject",
        "user_domain_name": "Default",
        "project_domain_name": "Default",
        "region_name": "RegionOne",
        "interface": "public",
    }


def test_openstack_failure_is_reported_as_a_single_line_reason():
    """
    arrange: An OpenStack that cannot be reached.
    act: Reconcile.
    assert: A SecurityGroupReconcileError carries the reason on one line, so the Blocked
        status the charm sets stays readable.
    """

    def connect(**_auth_fields):
        raise RuntimeError("keystone unreachable:\nconnection refused")

    reconciler = SecurityGroupReconciler(_provider_config(), connect=connect)

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert str(exc_info.value) == "keystone unreachable: connection refused"


def test_openstack_failure_reason_is_bounded():
    """
    arrange: An OpenStack call that fails with an over-long message.
    act: Reconcile.
    assert: The reported reason is truncated, so it cannot crowd out the rest of a status
        message Juju shortens anyway.
    """

    def connect(**_auth_fields):
        raise RuntimeError("x" * (MAX_STATUS_REASON_LENGTH * 2))

    reconciler = SecurityGroupReconciler(_provider_config(), connect=connect)

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        reconciler.reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert len(str(exc_info.value)) == MAX_STATUS_REASON_LENGTH + len("...")
