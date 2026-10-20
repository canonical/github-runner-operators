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

import openstack

from charm_state import ProviderConfig, SecurityGroupRule

logger = logging.getLogger(__name__)

SECURITY_GROUP_NAME_PREFIX = "garm-"
SECURITY_GROUP_DESCRIPTION = (
    "Managed by the garm-configurator charm; its rules follow the security-group-rules option."
)

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
        self,
        provider_config: ProviderConfig,
        connect: typing.Callable[..., typing.Any] | None = None,
    ) -> None:
        """Initialise the reconciler.

        Args:
            provider_config: The OpenStack credentials and region to reconcile in.
            connect: The OpenStack SDK entrypoint, overridden by tests.
        """
        self._provider_config = provider_config
        # Typed as an opaque callable: the SDK's own signature is narrower than the
        # keyword arguments a connection takes, but is what must be called at runtime.
        self._connect: typing.Callable[..., typing.Any] = connect or openstack.connect

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
        # Nothing here may crash the hook: every failure is reported and retried, so the
        # next reconcile looks again either way.
        try:
            connection = self._connect(**self._auth_fields())
            try:
                group = self._ensure_group(connection, name)
                self._reconcile_rules(connection, group, rules)
                return str(group.id)
            finally:
                connection.close()
        except Exception as exc:
            raise SecurityGroupReconcileError(_reason(exc)) from exc

    def _auth_fields(self) -> dict[str, str]:
        """Return the keyword arguments the OpenStack SDK authenticates with."""
        config = self._provider_config
        return {
            "auth_url": config.auth_url,
            "username": config.username,
            "password": config.password,
            "project_name": config.project_name,
            "user_domain_name": config.user_domain_name,
            "project_domain_name": config.project_domain_name,
            "region_name": config.region_name,
            "interface": "public",
        }

    def _ensure_group(self, connection: typing.Any, name: str) -> typing.Any:
        """Return the named group, creating it when the project has none.

        Args:
            connection: The authenticated OpenStack connection.
            name: The group name.

        Returns:
            The security group this charm manages.
        """
        groups = sorted(
            (group for group in connection.network.security_groups() if group.name == name),
            key=_age,
        )
        if not groups:
            logger.info("Creating security group %s", name)
            return connection.network.create_security_group(
                name=name, description=SECURITY_GROUP_DESCRIPTION
            )
        return self._keep_one_group(connection, name, groups)

    def _keep_one_group(
        self, connection: typing.Any, name: str, groups: list[typing.Any]
    ) -> typing.Any:
        """Pick the group to converge and remove the duplicates nothing is using.

        OpenStack allows duplicate names, so two configurators can each create one. The
        survivor is the oldest group a port already attaches — the one protecting live
        runners — or the oldest group when none is attached. Every configurator makes the
        same choice, so the duplicates settle instead of deleting each other.

        A duplicate a port still attaches is left alone rather than deleted: OpenStack
        refuses that delete anyway, and trying it would block the reconcile over a group
        this charm does not manage. The warning names it, so an operator can move the port
        and remove the group.

        Args:
            connection: The authenticated OpenStack connection.
            name: The group name.
            groups: Every group of that name, oldest first.

        Returns:
            The security group this charm manages.
        """
        if len(groups) == 1:
            return groups[0]
        attached = {group.id: _ports_using(connection, group.id) for group in groups}
        survivor = next((group for group in groups if attached[group.id]), groups[0])
        for group in groups:
            if group.id == survivor.id:
                continue
            if attached[group.id]:
                logger.warning(
                    "Leaving security group %s (%s) in place: %d port(s) still attach it, and"
                    " %s (%s) is the group this charm manages",
                    name,
                    group.id,
                    len(attached[group.id]),
                    name,
                    survivor.id,
                )
                continue
            logger.warning(
                "Deleting duplicate security group %s (%s); %s (%s) is the group this charm"
                " manages",
                name,
                group.id,
                name,
                survivor.id,
            )
            _delete_unused_group(connection, group)
        return survivor

    def _reconcile_rules(
        self, connection: typing.Any, group: typing.Any, rules: list[SecurityGroupRule]
    ) -> None:
        """Add the configured rules, then remove the ones no longer configured.

        Additions come first so the group never loses a rule the runners may still be
        using — every runner of the scaleset carries this group.

        Args:
            connection: The authenticated OpenStack connection.
            group: The security group to converge.
            rules: The rules the group should hold.
        """
        desired = _desired_rule_fields(rules)
        observed = {
            _rule_identity(_observed_rule_fields(rule)): rule
            for rule in connection.network.security_group_rules(security_group_id=group.id)
        }
        for identity, fields in desired.items():
            if identity in observed:
                continue
            logger.info("Adding rule %s to security group %s", identity, group.name)
            connection.network.create_security_group_rule(security_group_id=group.id, **fields)
        for identity, rule in observed.items():
            if identity in desired:
                continue
            logger.info("Removing rule %s from security group %s", identity, group.name)
            connection.network.delete_security_group_rule(rule)


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
    for rule in rules:
        fields = _rule_fields(rule)
        desired.setdefault(_rule_identity(fields), fields)
    return desired


def _rule_fields(rule: SecurityGroupRule) -> dict[str, object]:
    """Translate a configured rule into the fields OpenStack creates it from."""
    return {
        "direction": rule.direction,
        "ethertype": rule.ethertype,
        # Neutron spells "every protocol" as a null protocol.
        "protocol": None if rule.protocol == "any" else rule.protocol,
        "port_range_min": rule.port_min,
        "port_range_max": rule.port_max,
        "remote_ip_prefix": rule.remote_ip_prefix,
    }


def _observed_rule_fields(rule: typing.Any) -> dict[str, object]:
    """Read the comparable fields of a rule as OpenStack reports it."""
    return {field: getattr(rule, field, None) for field in RULE_FIELDS}


def _rule_identity(fields: dict[str, object]) -> tuple:
    """Return what distinguishes one rule from another."""
    return tuple(fields.get(field) for field in RULE_FIELDS)


def _delete_unused_group(connection: typing.Any, group: typing.Any) -> None:
    """Delete a duplicate group, tolerating a port that attached it since the check.

    The port check above and this delete cannot be atomic, so OpenStack can still answer
    with a conflict. That is the same condition the check guards against, so it is logged
    rather than raised: a group a port uses must not block the reconcile. Every other
    failure — a refused permission, an unreachable API — still propagates.
    """
    try:
        connection.network.delete_security_group(group.id)
    except openstack.exceptions.ConflictException:
        logger.warning(
            "Could not delete security group %s (%s): a port attached it during the"
            " reconcile. Leaving it in place",
            group.name,
            group.id,
        )


def _ports_using(connection: typing.Any, group_id: str) -> list[typing.Any]:
    """Return the ports that attach a security group.

    The filter is applied again here because OpenStack ignores a query parameter it does
    not know, which would otherwise report every port in the project as attached.
    """
    return [
        port
        for port in connection.network.ports(security_group_ids=[group_id])
        if group_id in (port.security_group_ids or [])
    ]


def _age(group: typing.Any) -> str:
    """Return the sort key that puts the oldest security group first."""
    created = getattr(group, "created_at", None)
    return "" if created is None else str(created)


def _reason(exc: Exception) -> str:
    """Return a bounded, single-line reason for a status message."""
    reason = " ".join(str(exc).split()) or type(exc).__name__
    if len(reason) > MAX_STATUS_REASON_LENGTH:
        reason = f"{reason[:MAX_STATUS_REASON_LENGTH]}..."
    return reason
