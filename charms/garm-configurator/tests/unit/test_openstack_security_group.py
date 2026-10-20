# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the OpenStack security group reconciler."""

import typing

import keystoneauth1.exceptions.connection
import openstack.exceptions
import pytest
from openstack.network.v2 import security_group_rule as sdk_rules

from charm_state import ProviderConfig, SecurityGroupRule
from openstack_security_group import (
    SecurityGroupReconcileError,
    SecurityGroupReconciler,
    security_group_name,
)

SCALESET_NAME = "my-scaleset"
GROUP_NAME = "garm-my-scaleset"


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
        self.list_queries = []
        self.created_groups = []
        self.deleted_groups = []
        self.created_rules = []
        self.deleted_rules = []

    def security_groups(self, name=None, project_id=None):
        self.list_queries.append({"name": name, "project_id": project_id})
        return [group for group in self.groups if name is None or group.name == name]

    def create_security_group(self, name, description):
        # Neutron gives every new group one any-address egress rule per ethertype, whose
        # remote_ip_prefix is reported as None. A reconcile that compares prefixes literally
        # tries to create them again and is rejected with a 409, so the fake does too.
        group = _FakeGroup(
            name,
            gid=f"sg-{name}",
            rules=[
                _stored_rule(
                    direction="egress",
                    ethertype=ethertype,
                    protocol=None,
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
        group = self._group(security_group_id)
        if any(_neutron_key(rule) == _neutron_key(fields) for rule in group.rules):
            # Neutron refuses a duplicate rule with a 409, which is what strands a reconcile
            # that fails to recognise its own rule coming back.
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


def _neutron_key(rule):
    """Return the key Neutron uses to reject a duplicate rule.

    `securitygroups_db._rule_to_key` treats ``0.0.0.0/0``, ``::/0`` and an absent prefix as the
    same any-address value, which is the trap this fake exists to catch.
    """

    def field(name, default=None):
        if isinstance(rule, dict):
            value = rule.get(name, default)
        else:
            value = getattr(rule, "ether_type" if name == "ethertype" else name, default)
        return default if value is None else value

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


def _stored_rule(**fields):
    """Build a rule with the SDK's own resource, as OpenStack reports it.

    Using the real class is the point: it is what names the ethertype ``ether_type``, and a
    hand-rolled stand-in hidden the identity never matching, which rewrote the group on every
    reconcile.
    """
    rule_id = fields.pop("rule_id", 99)
    rule = sdk_rules.SecurityGroupRule.new(**fields)
    rule.id = f"rule-{rule_id}"
    return rule


SSH = SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)
SSH_FROM_SUBNET_RULE = SecurityGroupRule(
    direction="ingress", protocol="tcp", port_min=22, port_max=22, remote_ip_prefix="10.0.0.0/8"
)
EGRESS_ALL_V4_RULE = SecurityGroupRule(direction="egress", remote_ip_prefix="0.0.0.0/0")
EGRESS_ALL_V6_RULE = SecurityGroupRule(direction="egress", remote_ip_prefix="::/0")
SSH_INGRESS = _rule_fields("ingress", protocol="tcp", port_min=22, port_max=22)
SSH_INGRESS_FROM_SUBNET = _rule_fields(
    "ingress", protocol="tcp", port_min=22, port_max=22, prefix="10.0.0.0/8"
)
# What Neutron stores for an any-address egress rule: no prefix at all.
EGRESS_ANY_V4 = _rule_fields("egress", prefix=None)


def test_security_group_name_is_derived_from_the_scaleset_name():
    """
    arrange: A scaleset name.
    act: Derive the managed security group name.
    assert: The name is prefixed, so it is recognisably charm-managed and stable across
        restarts and upgrades.
    """
    assert security_group_name(SCALESET_NAME) == GROUP_NAME


@pytest.mark.parametrize(
    "existing_rules, configured_rules, expected_created, expected_deleted, expected_group_id",
    [
        pytest.param(
            None,
            [SSH_FROM_SUBNET_RULE, EGRESS_ALL_V4_RULE],
            [SSH_INGRESS_FROM_SUBNET],
            ["rule-default-IPv6"],
            f"sg-{GROUP_NAME}",
            id="create-group",
        ),
        pytest.param(
            None,
            [EGRESS_ALL_V4_RULE, EGRESS_ALL_V6_RULE],
            [],
            [],
            f"sg-{GROUP_NAME}",
            id="default-config-matches-neutron-defaults",
        ),
        pytest.param(
            [_stored_rule(**SSH_INGRESS), _stored_rule(**EGRESS_ANY_V4)],
            [SSH, EGRESS_ALL_V4_RULE],
            [],
            [],
            "sg-existing",
            id="reuse-unchanged",
        ),
        pytest.param(
            None,
            [SSH, SSH, EGRESS_ALL_V4_RULE],
            [SSH_INGRESS],
            ["rule-default-IPv6"],
            f"sg-{GROUP_NAME}",
            id="dedupe-configured",
        ),
        pytest.param(
            [
                _stored_rule(**SSH_INGRESS, rule_id=1),
                _stored_rule(
                    **_rule_fields("ingress", protocol="tcp", port_min=8080, port_max=8080),
                    rule_id=2,
                ),
            ],
            [SSH, EGRESS_ALL_V4_RULE],
            [EGRESS_ANY_V4],
            ["rule-2"],
            "sg-existing",
            id="delete-stale-rule",
        ),
        pytest.param(
            [
                _stored_rule(
                    **_rule_fields("ingress", protocol="tcp", port_min=3389, port_max=3389),
                    rule_id=7,
                )
            ],
            [EGRESS_ALL_V4_RULE],
            [EGRESS_ANY_V4],
            ["rule-7"],
            "sg-existing",
            id="delete-rule-added-by-hand",
        ),
    ],
)
def test_rules_converge_to_the_configured_set(
    sdk, existing_rules, configured_rules, expected_created, expected_deleted, expected_group_id
):
    """
    arrange: A project whose group holds *existing_rules*, or no group at all when it is None.
    act: Reconcile *configured_rules*.
    assert: The group ends up holding exactly those rules — created once each, with anything
        else removed — and the reconcile reports the group it kept or created.
    """
    groups = (
        []
        if existing_rules is None
        else [_FakeGroup(GROUP_NAME, gid="sg-existing", rules=existing_rules)]
    )
    network = _FakeNetwork(groups)

    group_id = _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=configured_rules)

    assert group_id == expected_group_id
    assert network.created_rules == expected_created
    assert network.deleted_rules == expected_deleted


def test_a_duplicate_identical_rule_is_removed(sdk):
    """
    arrange: A group holding the same rule twice, which Neutron accepts.
    act: Reconcile that one rule.
    assert: The surplus copy is deleted, so "the group holds exactly the configured rules" is
        true rather than merely "it holds at least them".
    """
    network = _FakeNetwork(
        [
            _FakeGroup(
                GROUP_NAME,
                gid="sg-existing",
                rules=[
                    _stored_rule(**EGRESS_ANY_V4, rule_id=1),
                    _stored_rule(**EGRESS_ANY_V4, rule_id=2),
                ],
            )
        ]
    )

    _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert network.created_rules == []
    assert network.deleted_rules == ["rule-2"]


def test_reconciling_unchanged_rules_makes_no_change(sdk):
    """
    arrange: A group that already holds the configured rule, built from the SDK's own resource
        so the field names are the ones the API really returns.
    act: Reconcile twice.
    assert: Neither pass creates or deletes anything. Reading the ethertype under the wrong
        attribute name would leave every rule looking new and rewrite the group on every event.
    """
    network = _FakeNetwork(
        [_FakeGroup(GROUP_NAME, gid="sg-existing", rules=[_stored_rule(**EGRESS_ANY_V4)])]
    )
    reconciler = _reconciler(sdk, network)

    reconciler.reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])
    reconciler.reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert network.created_rules == []
    assert network.deleted_rules == []


@pytest.mark.parametrize(
    "ports, delete_error, expected_group_id, expected_deleted, expected_error",
    [
        pytest.param([], None, "sg-older", ["sg-newer"], None, id="no-ports-keep-oldest"),
        pytest.param(
            [_FakePort("sg-newer")], None, "sg-newer", ["sg-older"], None, id="attached-wins"
        ),
        pytest.param(
            [_FakePort("sg-newer"), _FakePort("sg-older")],
            None,
            "sg-older",
            [],
            None,
            id="both-attached-keep-both",
        ),
        pytest.param(
            [],
            openstack.exceptions.ConflictException("Security Group in use"),
            "sg-older",
            [],
            None,
            id="port-attaches-during-delete",
        ),
        pytest.param(
            [],
            openstack.exceptions.ForbiddenException("Policy does not allow this request"),
            "sg-older",
            [],
            None,
            id="delete-forbidden-is-tolerated",
        ),
        pytest.param(
            [],
            openstack.exceptions.NotFoundException("no such security group"),
            None,
            None,
            "no such security group",
            id="delete-refused-for-another-reason",
        ),
    ],
)
def test_duplicate_groups_converge_on_one_group(
    sdk, ports, delete_error, expected_group_id, expected_deleted, expected_error
):
    """
    arrange: Two groups sharing the managed name, with *ports* attaching them, and an OpenStack
        whose delete raises *delete_error* when one is set.
    act: Reconcile.
    assert: The charm keeps the group protecting live runners, or the oldest when none is
        attached, deletes only duplicates no port uses, and tolerates a port attaching during
        the delete or a role that may not delete groups — while any other delete failure still
        blocks.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-newer", created_at="2026-02-01T00:00:00Z"),
            _FakeGroup(GROUP_NAME, gid="sg-older", created_at="2026-01-01T00:00:00Z"),
        ],
        ports=ports,
    )
    if delete_error is not None:

        def fail(security_group):
            raise delete_error

        setattr(network, "delete_security_group", fail)

    if expected_error is not None:
        with pytest.raises(SecurityGroupReconcileError) as exc_info:
            _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])
        assert expected_error in str(exc_info.value)
        return

    group_id = _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert group_id == expected_group_id
    assert network.deleted_groups == expected_deleted


def test_delete_removes_the_groups_of_that_name(sdk):
    """
    arrange: One group with the managed name, and one belonging to something else.
    act: Delete the managed group.
    assert: Only that group goes, and the call reports it did something, so clearing the
        option does not leave the group behind.
    """
    network = _FakeNetwork(
        [
            _FakeGroup(GROUP_NAME, gid="sg-managed"),
            _FakeGroup("someone-elses-group", gid="sg-other"),
        ]
    )

    deleted = _reconciler(sdk, network).delete(name=GROUP_NAME)

    assert deleted is True
    assert network.deleted_groups == ["sg-managed"]


def test_delete_reports_nothing_when_there_is_no_group(sdk):
    """
    arrange: A project where the charm never created a group.
    act: Delete it.
    assert: Nothing is deleted and nothing raises, so an opt-out deployment does not fail.
    """
    network = _FakeNetwork()

    assert _reconciler(sdk, network).delete(name=GROUP_NAME) is False
    assert network.deleted_groups == []


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(openstack.exceptions.ConflictException("Security Group in use"), id="in-use"),
        pytest.param(
            openstack.exceptions.ForbiddenException("Policy does not allow this request"),
            id="not-permitted",
        ),
    ],
)
def test_delete_tolerates_a_group_it_may_not_remove(sdk, error):
    """
    arrange: A group a port still attaches, or credentials that may not delete groups.
    act: Delete it.
    assert: The call reports nothing deleted and does not raise, because it runs while the
        application is being removed and must not block that.
    """

    class _Refuses(_FakeNetwork):
        def delete_security_group(self, security_group):
            raise error

    network = _Refuses([_FakeGroup(GROUP_NAME, gid="sg-managed")])

    assert _reconciler(sdk, network).delete(name=GROUP_NAME) is False


def test_delete_reports_an_unreachable_api_without_raising(monkeypatch):
    """
    arrange: An OpenStack that cannot be reached.
    act: Delete the managed group.
    assert: The failure is logged and reported as nothing deleted, because the call runs while
        the application is being removed and must not block it.
    """

    def connect(**_auth_fields):
        raise openstack.exceptions.SDKException("neutron unreachable")

    monkeypatch.setattr("openstack_security_group.openstack.connect", connect)

    assert SecurityGroupReconciler(_provider_config()).delete(name=GROUP_NAME) is False


def test_the_group_list_is_scoped_to_the_project(sdk):
    """
    arrange: A project with a group of the managed name.
    act: Reconcile.
    assert: The list asks for that name in this project only, so admin-scoped credentials
        cannot mistake another project's group for a duplicate.
    """
    network = _FakeNetwork([_FakeGroup(GROUP_NAME, gid="sg-only")])

    _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert network.list_queries == [{"name": GROUP_NAME, "project_id": "project-id"}]


def test_ports_are_only_listed_when_the_name_is_duplicated(sdk):
    """
    arrange: A single group with the managed name, the normal case.
    act: Reconcile.
    assert: No port listing happens, so a steady-state reconcile costs no extra API calls.
    """
    network = _FakeNetwork([_FakeGroup(GROUP_NAME, gid="sg-only")])

    _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

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

    group_id = _reconciler(sdk, network).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert group_id == "sg-older"
    assert network.deleted_groups == ["sg-newer"]


def test_connection_is_closed_after_a_successful_reconcile(sdk):
    """
    arrange: A working connection.
    act: Reconcile.
    assert: The connection is closed, so repeated reconciles do not leak sessions.
    """
    _reconciler(sdk, _FakeNetwork()).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert sdk.connection.closed is True


def test_authentication_uses_the_provider_config(sdk):
    """
    arrange: The charm state's provider credentials.
    act: Reconcile.
    assert: The SDK is given those credentials and the configured region, so the connection
        resolves the same endpoints the provider does.
    """
    _reconciler(sdk, _FakeNetwork()).reconcile(name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE])

    assert sdk.auth == {
        "auth_url": "https://keystone.example.com:5000/v3",
        "username": "admin",
        "password": "s3cr3t",
        "project_name": "myproject",
        "user_domain_name": "Default",
        "project_domain_name": "Default",
        "region_name": "RegionOne",
        "api_timeout": 30,
    }


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(openstack.exceptions.SDKException("neutron refused the request"), id="sdk"),
        pytest.param(
            keystoneauth1.exceptions.connection.ConnectFailure(
                "keystone unreachable:\nconnection refused"
            ),
            id="keystoneauth",
        ),
    ],
)
def test_openstack_failure_is_reported_as_a_single_line_reason(monkeypatch, error):
    """
    arrange: An OpenStack failure, from the SDK's hierarchy or from keystoneauth's — an
        unreachable Keystone never reaches the SDK's base class.
    act: Reconcile.
    assert: The error carries the whole reason on one line for the log, so debug-log shows what
        went wrong without a multi-line traceback.
    """

    def connect(**_auth_fields):
        raise error

    monkeypatch.setattr("openstack_security_group.openstack.connect", connect)

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        SecurityGroupReconciler(_provider_config()).reconcile(
            name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE]
        )

    assert str(exc_info.value) == " ".join(str(error).split())


def test_an_unexpected_failure_is_not_hidden(monkeypatch):
    """
    arrange: A failure outside the SDK's and keystoneauth's hierarchies, as a bug in this code
        would raise.
    act: Reconcile.
    assert: It propagates, so a programming error fails the hook loudly instead of being
        reported as a blocked OpenStack reconcile the next event would retry.
    """

    def connect(**_auth_fields):
        raise RuntimeError("a bug, not an OpenStack failure")

    monkeypatch.setattr("openstack_security_group.openstack.connect", connect)

    with pytest.raises(RuntimeError):
        SecurityGroupReconciler(_provider_config()).reconcile(
            name=GROUP_NAME, rules=[EGRESS_ALL_V4_RULE]
        )
