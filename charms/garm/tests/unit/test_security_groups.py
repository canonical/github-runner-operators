# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the security group reconciler the GARM charm runs."""

import typing

import keystoneauth1.exceptions.connection
import openstack.exceptions
import pytest
from openstack.network.v2 import security_group_rule as sdk_rules

from charm_state import SecurityGroupRule
from security_groups import (
    SECURITY_GROUP_DESCRIPTION,
    SecurityGroupReconcileError,
    SecurityGroupReconciler,
    security_group_name,
)

SCALESET_NAME = "my-scaleset"
GROUP_NAME = "garm-my-scaleset"
OWNER = "garm"
DESCRIPTION = SECURITY_GROUP_DESCRIPTION.format(OWNER)
PROVIDER_CONFIG = {
    "unit_name": "garm-configurator-0",
    "auth_url": "https://keystone.example.com:5000/v3",
    "username": "admin",
    "password": "s3cr3t",
    "project_name": "myproject",
    "user_domain_name": "Default",
    "project_domain_name": "Default",
    "region_name": "RegionOne",
    "network": "external-net",
}


class _FakeGroup:
    """A security group as the SDK reports it."""

    def __init__(self, name, gid="sg-1", description=DESCRIPTION, rules=()):
        self.id = gid
        self.name = name
        self.description = description
        self.rules = list(rules)


class _FakeNetwork:
    """The network service of a fake OpenStack connection, with Neutron's rule semantics."""

    def __init__(self, groups=()):
        self.groups = list(groups)
        self.list_queries = []
        self.created_groups = []
        self.deleted_groups = []
        self.created_rules = []
        self.deleted_rules = []

    def security_groups(self, project_id=None):
        self.list_queries.append(project_id)
        return list(self.groups)

    def create_security_group(self, name, description):
        # Neutron gives a new group one any-address egress rule per ethertype, reported with
        # no remote_ip_prefix; a reconcile that compares prefixes literally would try to
        # create them again and be refused.
        group = _FakeGroup(
            name,
            gid=f"sg-{name}",
            description=description,
            rules=[
                _stored_rule(
                    direction="egress",
                    ethertype=ethertype,
                    remote_ip_prefix=None,
                    rule_id=f"default-{ethertype}",
                )
                for ethertype in ("IPv4", "IPv6")
            ],
        )
        self.groups.append(group)
        self.created_groups.append(name)
        return group

    def delete_security_group(self, security_group):
        self.deleted_groups.append(security_group)
        self.groups = [group for group in self.groups if group.id != security_group]

    def security_group_rules(self, security_group_id):
        return list(self._group(security_group_id).rules)

    def create_security_group_rule(self, security_group_id, **fields):
        group = self._group(security_group_id)
        if any(_neutron_key(rule) == _neutron_key(fields) for rule in group.rules):
            raise openstack.exceptions.ConflictException("Security group rule already exists")
        self.created_rules.append(fields)
        rule = sdk_rules.SecurityGroupRule.new(**fields)
        rule.id = f"rule-created-{len(self.created_rules)}"
        group.rules.append(rule)
        return rule

    def delete_security_group_rule(self, security_group_rule):
        self.deleted_rules.append(security_group_rule.id)
        for group in self.groups:
            group.rules = [rule for rule in group.rules if rule.id != security_group_rule.id]

    def _group(self, group_id):
        return next(group for group in self.groups if group.id == group_id)


class _FakeConnection:
    """A fake OpenStack connection holding one network service."""

    current_project_id = "project-id"

    def __init__(self, network):
        self.network = network
        self.closed = False

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        self.close()


@pytest.fixture(name="sdk", autouse=True)
def sdk_fixture(monkeypatch):
    """Keep every test off the real OpenStack SDK entrypoint."""
    connection = _FakeConnection(_FakeNetwork())
    calls: dict[str, typing.Any] = {"connection": connection}

    def connect(**auth_fields):
        calls["auth"] = auth_fields
        return connection

    monkeypatch.setattr("security_groups.openstack.connect", connect)
    return calls


def _reconciler(sdk, network=None):
    """Build a reconciler whose stubbed connection serves *network*, when given."""
    if network is not None:
        sdk["connection"].network = network
        sdk["connection"].closed = False
    return SecurityGroupReconciler(provider_config=PROVIDER_CONFIG, owner=OWNER)


def _neutron_key(rule):
    """Return the key Neutron uses to reject a duplicate rule."""

    def field(name):
        if isinstance(rule, dict):
            return rule.get(name)
        return getattr(rule, "ether_type" if name == "ethertype" else name, None)

    return (
        field("direction"),
        field("ethertype"),
        None if field("protocol") in (None, "any") else field("protocol"),
        field("port_range_min"),
        field("port_range_max"),
        None
        if field("remote_ip_prefix") in (None, "0.0.0.0/0", "::/0")
        else field("remote_ip_prefix"),
        field("remote_group_id"),
        field("remote_address_group_id"),
    )


def _stored_ports(port):
    """Fields for an ingress tcp rule on one port, as Neutron stores it."""
    return {
        "direction": "ingress",
        "ethertype": "IPv4",
        "protocol": "tcp",
        "port_range_min": port,
        "port_range_max": port,
        "remote_ip_prefix": None,
    }


def _stored_rule(**fields):
    """Build a rule with the SDK's own resource, as OpenStack reports it."""
    rule_id = fields.pop("rule_id", 99)
    rule = sdk_rules.SecurityGroupRule.new(**fields)
    rule.id = f"rule-{rule_id}"
    return rule


SSH = SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)
EGRESS_V4 = SecurityGroupRule(direction="egress", remote_ip_prefix="0.0.0.0/0")
EGRESS_V6 = SecurityGroupRule(direction="egress", remote_ip_prefix="::/0")
SSH_FIELDS = {
    "direction": "ingress",
    "ethertype": "IPv4",
    "protocol": "tcp",
    "port_range_min": 22,
    "port_range_max": 22,
    "remote_ip_prefix": None,
}
EGRESS_V4_FIELDS = {
    "direction": "egress",
    "ethertype": "IPv4",
    "protocol": None,
    "port_range_min": None,
    "port_range_max": None,
    "remote_ip_prefix": None,
}
EGRESS_V6_FIELDS = {**EGRESS_V4_FIELDS, "ethertype": "IPv6"}


def test_the_group_name_is_derived_from_the_scaleset_name():
    """
    arrange: A scale set name.
    act: Derive its group name.
    assert: The name is prefixed and derived from the name alone, so an upgrade reuses the group
        the configurator-side implementation created rather than replacing it.
    """
    assert security_group_name(scaleset_name=SCALESET_NAME) == GROUP_NAME


def test_a_missing_group_is_created_and_its_id_returned(sdk):
    """
    arrange: A tenant without the scale set's group.
    act: Reconcile the scale set's rules.
    assert: The group is created with the owning application in its description, and the id is
        returned for the provider to attach.
    """
    network = _FakeNetwork()

    groups = _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH, EGRESS_V4]})

    assert network.created_groups == [GROUP_NAME]
    assert network.groups[0].description == DESCRIPTION
    assert groups == {SCALESET_NAME: f"sg-{GROUP_NAME}"}


def test_the_default_rules_match_the_group_neutron_creates(sdk):
    """
    arrange: A tenant without the group, and the configurator's default rules.
    act: Reconcile.
    assert: Nothing is added or removed, because a new group already carries those egress rules
        spelled with no prefix.
    """
    network = _FakeNetwork()

    _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [EGRESS_V4, EGRESS_V6]})

    assert network.created_rules == []
    assert network.deleted_rules == []


def test_the_published_rules_are_authoritative(sdk):
    """
    arrange: A group holding a rule the operator removed and missing one they added.
    act: Reconcile the published list.
    assert: The missing rule is created and the stale one deleted, so the group matches the
        published policy exactly.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(
                GROUP_NAME,
                rules=[
                    _stored_rule(**SSH_FIELDS, rule_id=1),
                    _stored_rule(**_stored_ports(8080), rule_id=2),
                ],
            )
        ]
    )

    _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH, EGRESS_V4]})

    assert network.created_rules == [EGRESS_V4_FIELDS]
    assert network.deleted_rules == ["rule-2"]


def test_an_existing_marked_group_is_reused(sdk):
    """
    arrange: A group this application created, already holding the published rules.
    act: Reconcile again.
    assert: Nothing is created or deleted, so a steady-state pass makes no writes.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(
                GROUP_NAME,
                gid="sg-existing",
                rules=[
                    _stored_rule(**SSH_FIELDS, rule_id=1),
                    _stored_rule(**EGRESS_V4_FIELDS, rule_id=2),
                ],
            )
        ]
    )

    groups = _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH, EGRESS_V4]})

    assert groups == {SCALESET_NAME: "sg-existing"}
    assert network.created_groups == []
    assert network.created_rules == []
    assert network.deleted_rules == []


def test_a_group_no_scaleset_claims_is_deleted(sdk):
    """
    arrange: A group this application created for a scale set that no longer exists, and one
        for a scale set that does.
    act: Reconcile the surviving scale set.
    assert: The orphan is deleted, so renames and removals do not leak groups against the quota.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-kept", rules=[_stored_rule(**SSH_FIELDS)]),
            _FakeGroup("garm-renamed-away", gid="sg-orphan"),
        ]
    )

    _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH]})

    assert network.deleted_groups == ["sg-orphan"]


def test_another_applications_group_is_left_alone(sdk):
    """
    arrange: A group with the managed name pattern that another GARM application owns.
    act: Reconcile.
    assert: It is not deleted, so two applications sharing a project cannot delete each other's
        groups.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-mine", rules=[_stored_rule(**SSH_FIELDS)]),
            _FakeGroup("garm-other", gid="sg-theirs", description="Managed by garm-b charm."),
        ]
    )

    _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH]})

    assert network.deleted_groups == []


def test_a_group_still_in_use_is_kept(sdk):
    """
    arrange: An unclaimed group a port still attaches, as happens for hours after a scale set
        is deleted.
    act: Reconcile.
    assert: The refusal is logged and the pass continues, because it resolves on a later pass.
    """

    class _InUse(_FakeNetwork):
        def __init__(self, groups=()):
            super().__init__(groups)
            self.attempts = 0

        def delete_security_group(self, security_group):
            self.attempts += 1
            raise openstack.exceptions.ConflictException("Security Group in use")

    network = _InUse(
        [
            _FakeGroup(GROUP_NAME, gid="sg-kept", rules=[_stored_rule(**SSH_FIELDS)]),
            _FakeGroup("garm-orphan", gid="sg-orphan"),
        ]
    )

    _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH]})

    assert network.deleted_groups == []
    assert network.attempts == 1


def test_a_hook_without_delete_permission_still_converges(sdk):
    """
    arrange: Credentials that may create and update groups but not delete them.
    act: Reconcile a scale set whose group exists and an orphan that cannot be deleted.
    assert: The scale set still gets its id and the pass does not fail, so a missing delete
        permission degrades the sweep rather than the feature.
    """

    class _Forbidden(_FakeNetwork):
        def delete_security_group(self, security_group):
            raise openstack.exceptions.ForbiddenException("Policy does not allow this request")

    network = _Forbidden(
        [
            _FakeGroup(GROUP_NAME, gid="sg-kept", rules=[_stored_rule(**SSH_FIELDS)]),
            _FakeGroup("garm-orphan", gid="sg-orphan"),
        ]
    )

    groups = _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH]})

    assert groups == {SCALESET_NAME: "sg-kept"}


def test_a_scale_set_that_opts_out_has_its_group_deleted(sdk):
    """
    arrange: A group this application created, and a scale set that publishes no rules.
    act: Reconcile an empty mapping, as the opt-out does.
    assert: The group is deleted, so turning the feature off does not leak it.
    """
    network = _FakeNetwork([_FakeGroup(GROUP_NAME, gid="sg-orphan")])

    groups = _reconciler(sdk, network).reconcile(rules={})

    assert groups == {}
    assert network.deleted_groups == ["sg-orphan"]


def test_a_duplicate_group_name_is_also_swept(sdk):
    """
    arrange: Two groups this application created with the same name, from an interrupted pass.
    act: Reconcile the scale set.
    assert: One is kept and the other deleted, because a group that is never claimed is never
        removed either.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-kept", rules=[_stored_rule(**SSH_FIELDS)]),
            _FakeGroup(GROUP_NAME, gid="sg-duplicate"),
        ]
    )

    groups = _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH]})

    assert groups == {SCALESET_NAME: "sg-kept"}
    assert network.deleted_groups == ["sg-duplicate"]


def test_a_group_deleted_by_a_concurrent_pass_is_not_an_error(sdk):
    """
    arrange: An unclaimed group another pass removes first.
    act: Reconcile.
    assert: The pass completes, because the outcome is the one it wanted.
    """

    class _Gone(_FakeNetwork):
        def delete_security_group(self, security_group):
            raise openstack.exceptions.NotFoundException("no such security group")

    network = _Gone([_FakeGroup("garm-orphan", gid="sg-gone")])

    assert _reconciler(sdk, network).reconcile(rules={}) == {}


def test_the_group_list_is_scoped_to_the_project(sdk):
    """
    arrange: A tenant with a group.
    act: Reconcile.
    assert: The list asks for this project only, so admin-scoped credentials cannot sweep
        another project's groups.
    """
    network = _FakeNetwork([_FakeGroup(GROUP_NAME, gid="sg-only")])

    _reconciler(sdk, network).reconcile(rules={SCALESET_NAME: [SSH]})

    assert network.list_queries == ["project-id"]


def test_delete_removes_every_group_this_application_created(sdk):
    """
    arrange: Groups this application created, and one it did not.
    act: Delete, as the remove hook does.
    assert: Only its own groups go, and the call reports it did something.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-a"),
            _FakeGroup("garm-other", gid="sg-b"),
            _FakeGroup("garm-theirs", gid="sg-c", description="Managed by garm-b charm."),
        ]
    )

    deleted = _reconciler(sdk, network).delete()

    assert deleted is True
    assert network.deleted_groups == ["sg-a", "sg-b"]


def test_an_openstack_failure_is_reported_to_the_caller(monkeypatch):
    """
    arrange: An OpenStack that cannot be reached.
    act: Reconcile.
    assert: The failure reaches the caller as one short line, so it can skip those scale sets
        and report them, rather than creating runners without the group.
    """

    def connect(**_auth_fields):
        raise keystoneauth1.exceptions.connection.ConnectFailure("keystone unreachable")

    monkeypatch.setattr("security_groups.openstack.connect", connect)

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        SecurityGroupReconciler(provider_config=PROVIDER_CONFIG, owner=OWNER).reconcile(
            rules={SCALESET_NAME: [SSH]}
        )

    assert str(exc_info.value) == "keystone unreachable"


def test_delete_never_raises(monkeypatch):
    """
    arrange: An OpenStack that cannot be reached while the application is being removed.
    act: Delete.
    assert: Nothing is reported deleted and nothing raises, so removal is not blocked.
    """

    def connect(**_auth_fields):
        raise openstack.exceptions.SDKException("neutron unreachable")

    monkeypatch.setattr("security_groups.openstack.connect", connect)

    assert SecurityGroupReconciler(provider_config=PROVIDER_CONFIG, owner=OWNER).delete() is False
