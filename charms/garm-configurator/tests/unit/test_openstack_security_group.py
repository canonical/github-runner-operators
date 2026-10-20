# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the OpenStack security group reconciler."""

import typing

import pytest

from charm_state import ProviderConfig, SecurityGroupRule
from openstack_client import OpenStackClientError
from openstack_security_group import (
    MAX_STATUS_REASON_LENGTH,
    SecurityGroupReconcileError,
    SecurityGroupReconciler,
    security_group_name,
)

SCALESET_NAME = "my-scaleset"
GROUP_NAME = "garm-my-scaleset"


class FakeNetworkClient:
    """An in-memory Neutron API holding one project's security groups."""

    def __init__(self, groups: typing.Sequence[dict] = ()):
        self.groups = [dict(group, rules=list(group.get("rules", []))) for group in groups]
        self.created_groups: list[str] = []
        self.created_rules: list[dict] = []
        self.deleted_rules: list[str] = []
        self._next_id = 1

    def security_groups(self):
        return [{"id": group["id"], "name": group["name"]} for group in self.groups]

    def create_security_group(self, name, description):
        group = {"id": f"sg-{self._next_id}", "name": name, "rules": []}
        self._next_id += 1
        self.groups.append(group)
        self.created_groups.append(name)
        return group

    def security_group_rules(self, security_group_id):
        return list(self._group(security_group_id)["rules"])

    def create_security_group_rule(self, security_group_id, fields):
        rule = {"id": f"rule-{self._next_id}", **fields}
        self._next_id += 1
        self._group(security_group_id)["rules"].append(rule)
        self.created_rules.append(fields)
        return rule

    def delete_security_group_rule(self, rule_id):
        self.deleted_rules.append(rule_id)
        for group in self.groups:
            group["rules"] = [rule for rule in group["rules"] if rule["id"] != rule_id]

    def _group(self, group_id):
        return next(group for group in self.groups if group["id"] == group_id)


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


def _reconciler(client):
    """Build a reconciler over *client*."""
    return SecurityGroupReconciler(_provider_config(), client=client)


def _rule_fields(
    direction, protocol=None, port_min=None, port_max=None, prefix=None, ethertype="IPv4"
):
    """Build the fields Neutron creates one rule from."""
    return {
        "direction": direction,
        "ethertype": ethertype,
        "protocol": protocol,
        "port_range_min": port_min,
        "port_range_max": port_max,
        "remote_ip_prefix": prefix,
    }


def _stored_rule(**fields):
    """Build a rule as Neutron reports it, with the id it assigned."""
    return {"id": f"rule-{fields.pop('rule_id', 99)}", **fields}


EGRESS_V4 = _rule_fields("egress", prefix="0.0.0.0/0")
EGRESS_V6 = _rule_fields("egress", prefix="::/0", ethertype="IPv6")
SSH_INGRESS = _rule_fields("ingress", protocol="tcp", port_min=22, port_max=22)
SSH_INGRESS_FROM_SUBNET = _rule_fields(
    "ingress", protocol="tcp", port_min=22, port_max=22, prefix="10.0.0.0/8"
)


def test_security_group_name_is_derived_from_the_scaleset_name():
    """
    arrange: A scaleset name.
    act: Derive the managed security group name.
    assert: The name is prefixed, so it is recognisably charm-managed and stable across
        restarts and upgrades.
    """
    assert security_group_name(SCALESET_NAME) == GROUP_NAME


def test_missing_group_is_created_with_the_configured_and_default_egress_rules():
    """
    arrange: A project with no managed security group yet.
    act: Reconcile one ingress rule.
    assert: The group is created, holds that rule, and also allows all egress — without it a
        runner could not reach GitHub, because OpenStack attaches this group instead of the
        project's default group.
    """
    client = FakeNetworkClient()

    group_id = _reconciler(client).reconcile(
        GROUP_NAME,
        [
            SecurityGroupRule(
                direction="ingress",
                protocol="tcp",
                port_min=22,
                port_max=22,
                remote_ip_prefix="10.0.0.0/8",
            )
        ],
    )

    assert client.created_groups == [GROUP_NAME]
    assert client.created_rules == [SSH_INGRESS_FROM_SUBNET, EGRESS_V4, EGRESS_V6]
    assert group_id == "sg-1"


def test_configured_egress_rule_replaces_the_default_egress():
    """
    arrange: A project with no managed security group, and rules that state their own egress.
    act: Reconcile the rules.
    assert: Only the configured egress rule is created, so the operator's narrower egress is
        not widened by the charm's default.
    """
    client = FakeNetworkClient()

    _reconciler(client).reconcile(
        GROUP_NAME,
        [SecurityGroupRule(direction="egress", protocol="tcp", port_min=443, port_max=443)],
    )

    assert client.created_rules == [
        _rule_fields("egress", protocol="tcp", port_min=443, port_max=443)
    ]


def test_duplicate_configured_rules_are_created_once():
    """
    arrange: Rules that list the same ingress rule twice.
    act: Reconcile the rules.
    assert: One rule is created, so the group does not carry a duplicate the next reconcile
        would then have to remove.
    """
    client = FakeNetworkClient()
    ssh = SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)

    _reconciler(client).reconcile(GROUP_NAME, [ssh, ssh])

    assert client.created_rules == [SSH_INGRESS, EGRESS_V4, EGRESS_V6]


def test_existing_group_is_reused_and_its_matching_rules_are_left_alone():
    """
    arrange: A group that already holds the desired rules, with the ids Neutron assigned.
    act: Reconcile the same rules again.
    assert: The existing group and its rules are kept, so reconciling unchanged configuration
        only adds the rule that is missing.
    """
    client = FakeNetworkClient(
        [
            {
                "id": "sg-existing",
                "name": GROUP_NAME,
                "rules": [_stored_rule(**SSH_INGRESS), _stored_rule(**EGRESS_V4)],
            }
        ]
    )

    group_id = _reconciler(client).reconcile(
        GROUP_NAME, [SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)]
    )

    assert group_id == "sg-existing"
    assert client.created_groups == []
    assert client.deleted_rules == []
    assert client.created_rules == [EGRESS_V6]


def test_rules_no_longer_configured_are_deleted():
    """
    arrange: A group holding a rule the operator has since removed.
    act: Reconcile the remaining rules.
    assert: The stale rule is deleted and the kept one is not recreated, so the group matches
        the option exactly.
    """
    client = FakeNetworkClient(
        [
            {
                "id": "sg-existing",
                "name": GROUP_NAME,
                "rules": [
                    _stored_rule(**SSH_INGRESS, rule_id=1),
                    _stored_rule(
                        **_rule_fields("ingress", protocol="tcp", port_min=8080, port_max=8080),
                        rule_id=2,
                    ),
                ],
            }
        ]
    )

    _reconciler(client).reconcile(
        GROUP_NAME, [SecurityGroupRule(direction="ingress", protocol="tcp", port_min=22)]
    )

    assert client.deleted_rules == ["rule-2"]
    assert client.created_rules == [EGRESS_V4, EGRESS_V6]


def test_a_rule_added_by_hand_is_removed():
    """
    arrange: A group holding a rule the operator never configured, such as one added with the
        OpenStack CLI.
    act: Reconcile.
    assert: The rule is removed, because the option is the only source of the group's rules.
    """
    client = FakeNetworkClient(
        [
            {
                "id": "sg-existing",
                "name": GROUP_NAME,
                "rules": [
                    _stored_rule(
                        **_rule_fields("ingress", protocol="tcp", port_min=3389, port_max=3389),
                        rule_id=7,
                    )
                ],
            }
        ]
    )

    _reconciler(client).reconcile(GROUP_NAME, [])

    assert client.deleted_rules == ["rule-7"]
    assert client.created_rules == [EGRESS_V4, EGRESS_V6]


def test_ambiguous_group_name_is_reported_rather_than_guessed():
    """
    arrange: Two security groups sharing the managed name.
    act: Reconcile.
    assert: The reconcile fails, because picking one of the two would converge the wrong group.
    """
    client = FakeNetworkClient(
        [
            {"id": "sg-1", "name": GROUP_NAME},
            {"id": "sg-2", "name": GROUP_NAME},
        ]
    )

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        _reconciler(client).reconcile(GROUP_NAME, [])

    assert str(exc_info.value) == f"OpenStack holds 2 security groups named {GROUP_NAME}"


def test_openstack_failure_is_reported_as_a_single_line_reason():
    """
    arrange: An OpenStack that cannot be reached.
    act: Reconcile.
    assert: A SecurityGroupReconcileError carries the reason on one line, so the Blocked
        status the charm sets stays readable.
    """

    class _UnreachableClient:
        def security_groups(self):
            raise OpenStackClientError("cannot reach https://keystone:\nconnection refused")

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        _reconciler(_UnreachableClient()).reconcile(GROUP_NAME, [])

    assert str(exc_info.value) == "cannot reach https://keystone: connection refused"


def test_openstack_failure_reason_is_bounded():
    """
    arrange: An OpenStack call that fails with an over-long message.
    act: Reconcile.
    assert: The reported reason is truncated, so it cannot crowd out the rest of a status
        message Juju shortens anyway.
    """

    class _UnreachableClient:
        def security_groups(self):
            raise OpenStackClientError("x" * (MAX_STATUS_REASON_LENGTH * 2))

    with pytest.raises(SecurityGroupReconcileError) as exc_info:
        _reconciler(_UnreachableClient()).reconcile(GROUP_NAME, [])

    assert len(str(exc_info.value)) == MAX_STATUS_REASON_LENGTH + len("...")
