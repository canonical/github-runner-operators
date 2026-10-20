# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Reconcile the OpenStack security group a scaleset's runners are attached to.

Network isolation for the runners is policy, so the configurator owns it: it creates one
security group per scaleset and keeps its rules in line with the operator's
``security-group-rules``. The ``garm`` charm passes the group's id to the OpenStack provider
as the scaleset's ``security_groups`` extra spec.
"""

import logging
import typing

from charm_state import ProviderConfig, SecurityGroupRule
from openstack_client import NetworkClient, OpenStackClientError

logger = logging.getLogger(__name__)

SECURITY_GROUP_NAME_PREFIX = "garm-"
SECURITY_GROUP_DESCRIPTION = (
    "Managed by the garm-configurator charm; its rules follow the security-group-rules option."
)

# The egress the charm grants when the operator configures none. Attaching a security
# group replaces the project's default group, which allows all egress; without this a
# runner could not reach GitHub and would never register.
DEFAULT_EGRESS_PREFIXES = ("0.0.0.0/0", "::/0")

# What identifies a rule. Everything else OpenStack reports about one — its id, tenant,
# description — is either assigned by OpenStack or irrelevant to the desired state, so
# comparing only these makes the diff immune to it.
RULE_FIELDS = (
    "direction",
    "ethertype",
    "protocol",
    "port_range_min",
    "port_range_max",
    "remote_ip_prefix",
    "remote_group_id",
    "remote_address_group_id",
)

# Juju shows only the first line of a status message.
MAX_STATUS_REASON_LENGTH = 200


class SecurityGroupReconcileError(Exception):
    """Raised when the managed security group could not be reconciled with OpenStack."""


def security_group_name(scaleset_name: str) -> str:
    """Return the OpenStack name of the security group managed for a scaleset.

    The name is derived from the scaleset name alone, so a scaleset keeps the same group
    across charm upgrades and restarts.

    Args:
        scaleset_name: The scaleset name the operator configured.

    Returns:
        The name of the group that carries the scaleset's rules.
    """
    return f"{SECURITY_GROUP_NAME_PREFIX}{scaleset_name}"


class SecurityGroupReconciler:
    """Creates and converges one charm-managed OpenStack security group."""

    def __init__(
        self, provider_config: ProviderConfig, client: NetworkClient | None = None
    ) -> None:
        """Initialise the reconciler.

        Args:
            provider_config: The OpenStack credentials and region to reconcile in.
            client: The OpenStack client, overridden by tests.
        """
        self._provider_config = provider_config
        self._client = client

    def reconcile(self, name: str, rules: list[SecurityGroupRule]) -> str:
        """Create the group if it is missing, then converge its rules.

        Args:
            name: The group name, as returned by :func:`security_group_name`.
            rules: The rules the group should hold.

        Returns:
            The group's id, which the ``garm`` charm hands to the provider.

        Raises:
            SecurityGroupReconcileError: If OpenStack could not be reached or refused a
                change. The caller reports it and retries on the next event, because a
                rejected call says nothing about the group's final state.
        """
        client = self._client or NetworkClient(self._provider_config)
        try:
            group = self._ensure_group(client, name)
            self._reconcile_rules(client, group, rules)
            return str(group["id"])
        except OpenStackClientError as exc:
            raise SecurityGroupReconcileError(_reason(exc)) from exc

    def _ensure_group(self, client: NetworkClient, name: str) -> dict[str, typing.Any]:
        """Return the named group, creating it when the project has none.

        Args:
            client: The OpenStack client.
            name: The group name.

        Returns:
            The security group, as Neutron reports it.

        Raises:
            SecurityGroupReconcileError: If the name matches more than one group, which would
                make the reconcile pick one at random.
        """
        groups = [group for group in client.security_groups() if group.get("name") == name]
        if len(groups) > 1:
            raise SecurityGroupReconcileError(
                f"OpenStack holds {len(groups)} security groups named {name}"
            )
        if groups:
            return groups[0]
        logger.info("Creating security group %s", name)
        return client.create_security_group(name, SECURITY_GROUP_DESCRIPTION)

    def _reconcile_rules(
        self,
        client: NetworkClient,
        group: dict[str, typing.Any],
        rules: list[SecurityGroupRule],
    ) -> None:
        """Add the configured rules, then remove the ones no longer configured.

        Additions come first so the group never loses a rule the runners may still be
        using — every runner of the scaleset carries this group.

        Args:
            client: The OpenStack client.
            group: The security group to converge.
            rules: The rules the group should hold.
        """
        desired = _desired_rule_fields(rules)
        observed = {
            _rule_identity(_observed_rule_fields(rule)): rule
            for rule in client.security_group_rules(str(group["id"]))
        }
        for identity, fields in desired.items():
            if identity in observed:
                continue
            logger.info("Adding rule %s to security group %s", identity, group.get("name"))
            client.create_security_group_rule(str(group["id"]), fields)
        for identity, rule in observed.items():
            if identity in desired:
                continue
            logger.info("Removing rule %s from security group %s", identity, group.get("name"))
            client.delete_security_group_rule(str(rule["id"]))


def _desired_rule_fields(rules: list[SecurityGroupRule]) -> dict[tuple, dict[str, object]]:
    """Return the fields to create for each rule, keyed by rule identity.

    A rule the operator lists twice yields one entry, so the group does not collect
    duplicate rules that the next reconcile would then have to remove.

    Args:
        rules: The rules the group should hold.

    Returns:
        The rule fields to create, keyed by identity.
    """
    desired: dict[tuple, dict[str, object]] = {}
    for rule in _with_default_egress(rules):
        fields = _rule_fields(rule)
        desired.setdefault(_rule_identity(fields), fields)
    return desired


def _with_default_egress(rules: list[SecurityGroupRule]) -> list[SecurityGroupRule]:
    """Add the charm's default egress rules when the operator configured none.

    Args:
        rules: The rules the operator configured.

    Returns:
        The configured rules, plus all-egress rules for IPv4 and IPv6 when no egress rule
        was configured, so a runner can always reach GitHub.
    """
    if any(rule.direction == "egress" for rule in rules):
        return list(rules)
    return [
        *rules,
        *(
            SecurityGroupRule(direction="egress", remote_ip_prefix=prefix)
            for prefix in DEFAULT_EGRESS_PREFIXES
        ),
    ]


def _rule_fields(rule: SecurityGroupRule) -> dict[str, object]:
    """Translate a configured rule into the fields Neutron creates it from."""
    return {
        "direction": rule.direction,
        "ethertype": rule.ethertype,
        # Neutron spells "every protocol" as a null protocol.
        "protocol": None if rule.protocol == "any" else rule.protocol,
        "port_range_min": rule.port_min,
        "port_range_max": rule.port_max,
        "remote_ip_prefix": rule.remote_ip_prefix,
    }


def _observed_rule_fields(rule: dict[str, typing.Any]) -> dict[str, object]:
    """Read the comparable fields of a rule as Neutron reports it."""
    return {field: rule.get(field) for field in RULE_FIELDS}


def _rule_identity(fields: dict[str, object]) -> tuple:
    """Return what distinguishes one rule from another."""
    return tuple(fields.get(field) for field in RULE_FIELDS)


def _reason(exc: Exception) -> str:
    """Return a bounded, single-line reason for a status message."""
    reason = " ".join(str(exc).split()) or type(exc).__name__
    if len(reason) > MAX_STATUS_REASON_LENGTH:
        reason = f"{reason[:MAX_STATUS_REASON_LENGTH]}..."
    return reason
