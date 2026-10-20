# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the OpenStack security group reconciler."""

import typing

import keystoneauth1.exceptions.connection
import openstack.exceptions
import pytest

from charm_state import ProviderConfig, SecurityGroupRule
from openstack_security_group import (
    SecurityGroupReconcileError,
    SecurityGroupReconciler,
    security_group_name,
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
        self.created_rules.append(fields)
        rule = _FakeRule(**fields)
        self._group(security_group_id).rules.append(rule)
        return rule

    def delete_security_group_rule(self, security_group_rule):
        self.deleted_rules.append(security_group_rule.id)
        self._group_by_rule(security_group_rule).rules.remove(security_group_rule)

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


def _stored_rule(**fields):
    """Build a rule as OpenStack reports it, with the id it assigned."""
    return _FakeRule(id=f"rule-{fields.pop('rule_id', 99)}", **fields)


SSH = SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)
SSH_FROM_SUBNET_RULE = SecurityGroupRule(
    direction="ingress", protocol="tcp", port_min=22, port_max=22, remote_ip_prefix="10.0.0.0/8"
)
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


@pytest.mark.parametrize(
    "existing_rules, configured_rules, expected_created, expected_deleted, expected_group_id",
    [
        pytest.param(
            None,
            [SSH_FROM_SUBNET_RULE, EGRESS_ALL_V4_RULE],
            [SSH_INGRESS_FROM_SUBNET, EGRESS_ALL_V4],
            [],
            f"sg-{GROUP_NAME}",
            id="create-group",
        ),
        pytest.param(
            [_stored_rule(**SSH_INGRESS), _stored_rule(**EGRESS_ALL_V4)],
            [SSH, EGRESS_ALL_V4_RULE],
            [],
            [],
            "sg-existing",
            id="reuse-unchanged",
        ),
        pytest.param(
            None,
            [SSH, SSH, EGRESS_ALL_V4_RULE],
            [SSH_INGRESS, EGRESS_ALL_V4],
            [],
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
            [EGRESS_ALL_V4],
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
            [EGRESS_ALL_V4],
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
            None,
            None,
            "Policy does not allow",
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
        the delete — while any other delete failure still blocks.
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
