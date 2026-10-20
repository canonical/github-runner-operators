# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the OpenStack security group reconciler."""

import typing

import openstack.exceptions
import pytest

from charm_state import ProviderConfig, SecurityGroupRule
from openstack_security_group import (
    MAX_STATUS_REASON_LENGTH,
    SecurityGroupReconcileError,
    SecurityGroupReconciler,
    security_group_name,
    status_reason,
)

SCALESET_NAME = "my-scaleset"
GROUP_NAME = "garm-my-scaleset"


class _FakeRule:
    """A security group rule as the SDK reports it."""

    def __init__(self, **fields):
        for field in (
            "direction",
            "ethertype",
            "protocol",
            "port_range_min",
            "port_range_max",
            "remote_ip_prefix",
            "remote_group_id",
            "remote_address_group_id",
        ):
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


class _FakePort:
    """A port as the SDK reports it."""

    def __init__(self, *security_group_ids):
        self.security_group_ids = list(security_group_ids)


class _FakeNetwork:
    """The network service of a fake OpenStack connection."""

    def __init__(self, groups=(), ports=(), ignore_port_filter=False):
        self.groups = list(groups)
        self._ports = list(ports)
        # Models an OpenStack that ignores the filter it does not know.
        self._ignore_port_filter = ignore_port_filter
        self.port_queries = []
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

    def ports(self, security_group_ids=None):
        self.port_queries.append(security_group_ids)
        if self._ignore_port_filter:
            return list(self._ports)
        return [
            port for port in self._ports if set(security_group_ids) & set(port.security_group_ids)
        ]

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


class _FakeSdk:
    """The stubbed SDK entrypoint: the connection it hands out, and the auth it was given."""

    def __init__(self, monkeypatch):
        self.connection = _FakeConnection(_FakeNetwork())
        self.auth = None

        def connect(**auth_fields):
            self.auth = auth_fields
            return self.connection

        monkeypatch.setattr("openstack_security_group.openstack.connect", connect)


@pytest.fixture(name="sdk", autouse=True)
def sdk_fixture(monkeypatch):
    """Keep every test off the real OpenStack SDK entrypoint."""
    return _FakeSdk(monkeypatch)


def _reconciler(sdk, network=None):
    """Build a reconciler whose stubbed connection serves *network*, when given."""
    if network is not None:
        sdk.connection.network = network
        sdk.connection.closed = False
    return SecurityGroupReconciler(_provider_config())


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


def test_missing_group_is_created_with_the_configured_rules(sdk):
    """
    arrange: A project with no managed security group yet.
    act: Reconcile one ingress rule and one egress rule.
    assert: The group is created holding exactly those rules, because the option is the only
        source of the group's rules.
    """
    network = _FakeNetwork()

    group_id = _reconciler(sdk, network).reconcile(
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


def test_duplicate_configured_rules_are_created_once(sdk):
    """
    arrange: Rules that list the same ingress rule twice.
    act: Reconcile the rules.
    assert: One rule is created, so the group does not carry a duplicate the next reconcile
        would then have to remove.
    """
    network = _FakeNetwork()

    _reconciler(sdk, network).reconcile(GROUP_NAME, [SSH, SSH, EGRESS_ALL_V4_RULE])

    assert network.created_rules == [SSH_INGRESS, EGRESS_ALL_V4]


def test_existing_group_is_reused_and_its_matching_rules_are_left_alone(sdk):
    """
    arrange: A group that already holds the desired rules, with the ids OpenStack assigned.
    act: Reconcile the same rules again.
    assert: The existing group and its rules are kept, so reconciling unchanged configuration
        makes no change at all.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(
                GROUP_NAME,
                gid="sg-existing",
                rules=[_stored_rule(**SSH_INGRESS), _stored_rule(**EGRESS_ALL_V4)],
            )
        ]
    )

    group_id = _reconciler(sdk, network).reconcile(GROUP_NAME, [SSH, EGRESS_ALL_V4_RULE])

    assert group_id == "sg-existing"
    assert network.created_groups == []
    assert network.created_rules == []
    assert network.deleted_rules == []


def test_rules_no_longer_configured_are_deleted(sdk):
    """
    arrange: A group holding a rule the operator has since removed.
    act: Reconcile the remaining rules.
    assert: The stale rule is deleted, so the group matches the option exactly.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(
                GROUP_NAME,
                rules=[
                    _stored_rule(**SSH_INGRESS, rule_id=1),
                    _stored_rule(
                        **_rule_fields("ingress", protocol="tcp", port_min=8080, port_max=8080),
                        rule_id=2,
                    ),
                ],
            )
        ]
    )

    _reconciler(sdk, network).reconcile(GROUP_NAME, [SSH, EGRESS_ALL_V4_RULE])

    assert network.deleted_rules == ["rule-2"]
    assert network.created_rules == [EGRESS_ALL_V4]


def test_a_rule_added_by_hand_is_removed(sdk):
    """
    arrange: A group holding a rule the operator never configured, such as one added with the
        OpenStack CLI.
    act: Reconcile.
    assert: The rule is removed, because the option is the only source of the group's rules.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(
                GROUP_NAME,
                rules=[
                    _stored_rule(
                        **_rule_fields("ingress", protocol="tcp", port_min=3389, port_max=3389),
                        rule_id=7,
                    )
                ],
            )
        ]
    )

    _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert network.deleted_rules == ["rule-7"]
    assert network.created_rules == [EGRESS_ALL_V4]


def test_duplicate_groups_keep_the_oldest_and_delete_the_rest(sdk):
    """
    arrange: Two groups sharing the managed name and no port attaching either, as a race
        between two configurators leaves.
    act: Reconcile.
    assert: The older group is adopted and the unused newer one deleted, so the charm
        converges on one group instead of failing.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ]
    )

    group_id = _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert group_id == "sg-older"
    assert network.deleted_groups == ["sg-newer"]
    assert network.created_groups == []


def test_duplicate_a_port_still_attaches_is_kept_rather_than_deleted(sdk):
    """
    arrange: Two groups sharing the managed name, with runners attached to the newer one.
    act: Reconcile.
    assert: The attached group is adopted and the unused one deleted, so the charm converges
        on the group protecting live runners and never asks OpenStack to delete a group a port
        still uses.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ],
        ports=[_FakePort("sg-newer")],
    )

    group_id = _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert group_id == "sg-newer"
    assert network.deleted_groups == ["sg-older"]


def test_two_attached_duplicates_are_both_left_in_place(sdk):
    """
    arrange: Two groups sharing the managed name, with a port attaching each.
    act: Reconcile.
    assert: Neither is deleted — OpenStack would refuse — and the reconcile still succeeds on
        the oldest, leaving the operator to move the other port.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ],
        ports=[_FakePort("sg-newer"), _FakePort("sg-older")],
    )

    group_id = _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert group_id == "sg-older"
    assert network.deleted_groups == []
    assert network.created_groups == []


def test_a_port_attaching_during_the_reconcile_does_not_block(sdk):
    """
    arrange: An unused duplicate, and an OpenStack that reports a conflict because a port
        attached it between the port check and the delete.
    act: Reconcile.
    assert: The reconcile still succeeds on the survivor and the duplicate is left in place,
        so a race with a runner launch cannot block the unit.
    """

    class _Conflicts(_FakeNetwork):
        def delete_security_group(self, group_id):
            raise openstack.exceptions.ConflictException("Security Group in use")

    network = _Conflicts(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ]
    )

    group_id = _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert group_id == "sg-older"
    assert network.deleted_groups == []


def test_a_duplicate_delete_refused_for_another_reason_still_blocks(sdk):
    """
    arrange: An OpenStack that refuses the duplicate delete with a non-conflict error, such as
        a missing permission.
    act: Reconcile.
    assert: The failure blocks the unit, because it will not resolve on its own.
    """

    class _Forbidden(_FakeNetwork):
        def delete_security_group(self, group_id):
            raise openstack.exceptions.ForbiddenException("Policy does not allow this request")

    network = _Forbidden(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ]
    )

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert "Policy does not allow" in str(exc_info.value)


def test_ports_are_only_listed_when_the_name_is_duplicated(sdk):
    """
    arrange: A single group with the managed name, the normal case.
    act: Reconcile.
    assert: No port listing happens, so a steady-state reconcile costs no extra API calls.
    """
    network = _FakeNetwork([_FakeGroup(GROUP_NAME, gid="sg-only")])

    _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert network.port_queries == []


def test_port_filter_is_applied_locally_too(sdk):
    """
    arrange: An OpenStack that ignores the security group filter and returns every port.
    act: Reconcile a duplicated name.
    assert: Only ports naming the group count as attached, so an ignored filter cannot make an
        unused duplicate look used and keep it forever.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ],
        ports=[_FakePort("some-other-group")],
        ignore_port_filter=True,
    )

    group_id = _reconciler(sdk, network).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert group_id == "sg-older"
    assert network.deleted_groups == ["sg-newer"]


def test_connection_is_closed_after_a_successful_reconcile(sdk):
    """
    arrange: A working connection.
    act: Reconcile.
    assert: The connection is closed, so repeated reconciles do not leak sessions.
    """
    _reconciler(sdk, _FakeNetwork()).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert sdk.connection.closed is True


def test_authentication_uses_the_provider_config(sdk):
    """
    arrange: The charm state's provider credentials.
    act: Reconcile.
    assert: The SDK is given those credentials, the configured region, and the public endpoint
        interface.
    """
    _reconciler(sdk, _FakeNetwork()).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert sdk.auth == {
        "auth_url": "https://keystone.example.com:5000/v3",
        "username": "admin",
        "password": "s3cr3t",
        "project_name": "myproject",
        "user_domain_name": "Default",
        "project_domain_name": "Default",
        "region_name": "RegionOne",
        "interface": "public",
    }


def test_openstack_failure_is_reported_as_a_single_line_reason(monkeypatch):
    """
    arrange: An OpenStack that cannot be reached.
    act: Reconcile.
    assert: The error carries the whole reason on one line for the log, so debug-log shows what
        went wrong without a multi-line traceback.
    """

    def connect(**_auth_fields):
        raise RuntimeError("keystone unreachable:\nconnection refused")

    monkeypatch.setattr("openstack_security_group.openstack.connect", connect)

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        SecurityGroupReconciler(_provider_config()).reconcile(GROUP_NAME, [EGRESS_ALL_V4_RULE])

    assert str(exc_info.value) == "keystone unreachable: connection refused"


def test_status_reason_is_bounded():
    """
    arrange: A failure with a message far longer than a status line.
    act: Render it for the unit status.
    assert: The status text is truncated, so Juju shows the start of the reason rather than
        cutting it at an arbitrary point.
    """
    exc = SecurityGroupReconcileError("x" * (MAX_STATUS_REASON_LENGTH * 2))

    assert len(status_reason(exc)) == MAX_STATUS_REASON_LENGTH + len("...")
