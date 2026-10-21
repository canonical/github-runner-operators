# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures for the charm's unit tests."""

import typing

import openstack.exceptions
import pytest
from openstack.network.v2 import security_group_rule as sdk_rules

# The rules a configurator publishes by default: all egress, no ingress.
DEFAULT_RULES = (
    '[{"direction": "egress", "remote_ip_prefix": "0.0.0.0/0"},'
    ' {"direction": "egress", "remote_ip_prefix": "::/0"}]'
)


class _Rule:
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
            setattr(self, "ether_type" if field == "ethertype" else field, fields.get(field))
        self.id = fields.get("id", "rule-id")


class _Group:
    """A security group as the SDK reports it."""

    def __init__(self, name, gid="sg-1", description="", rules=()):
        self.id = gid
        self.name = name
        self.description = description
        self.rules = list(rules)


class _Network:
    """A Neutron that starts empty and behaves like the real one for this charm's calls."""

    def __init__(self):
        self.groups: list[_Group] = []
        self._created = 0

    def security_groups(self, project_id=None):
        return list(self.groups)

    def create_security_group(self, name, description):
        self._created += 1
        group = _Group(
            name,
            gid=f"sg-{self._created}",
            description=description,
            rules=[
                _Rule(
                    direction="egress",
                    ethertype=ethertype,
                    remote_ip_prefix=None,
                    id=f"default-{ethertype}",
                )
                for ethertype in ("IPv4", "IPv6")
            ],
        )
        self.groups.append(group)
        return group

    def delete_security_group(self, security_group):
        self.groups = [group for group in self.groups if group.id != security_group]

    def security_group_rules(self, security_group_id):
        return list(self._group(security_group_id).rules)

    def create_security_group_rule(self, security_group_id, **fields):
        self._created += 1
        rule = sdk_rules.SecurityGroupRule.new(**fields)
        rule.id = f"rule-{self._created}"
        self._group(security_group_id).rules.append(rule)
        return rule

    def delete_security_group_rule(self, security_group_rule):
        for group in self.groups:
            group.rules = [rule for rule in group.rules if rule.id != security_group_rule.id]

    def _group(self, group_id):
        return next(group for group in self.groups if group.id == group_id)


class _Connection:
    """A fake OpenStack connection holding one network service."""

    current_project_id = "project-id"

    def __init__(self):
        self.network = _Network()

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        self.close()


@pytest.fixture(autouse=True)
def openstack_tenant(monkeypatch) -> typing.Any:
    """Serve the security group reconciler from a fake tenant.

    The charm reconciles each tenant it has credentials for on every hook, so a test that does
    not stub it would reach Keystone. Tests that care about the calls patch or inspect it.
    """
    connection = _Connection()

    def connect(**_auth_fields):
        return connection

    monkeypatch.setattr("security_groups.openstack.connect", connect)
    return connection
