# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Reconcile the OpenStack security group a scaleset's runners are attached to.

Network isolation for the runners is policy, so the configurator owns it: it creates one
security group per scaleset and keeps its rules in line with the operator's
``security-group-rules``. The ``garm`` charm passes the group's id to the OpenStack provider
as the scaleset's ``security_groups`` extra spec.

Nothing the charms provide needs an ingress rule. GARM's remote shell rides the agent's
connection, which the runner opens to ``agent_url``, and a ``debug-ssh`` session is an
outbound tmate client on the runner; both are traffic the runner originates.
"""

import logging
import typing

import keystoneauth1.exceptions.base
import openstack

from charm_state import ProviderConfig, SecurityGroupRule

logger = logging.getLogger(__name__)

SECURITY_GROUP_NAME_PREFIX = "garm-"
SECURITY_GROUP_DESCRIPTION = (
    "Managed by the garm-configurator charm; its rules follow the security-group-rules option."
)

# What a reconcile can fail with: the SDK's own hierarchy for API responses, and
# keystoneauth's for transport and authentication, which never reach the SDK's base class —
# an unreachable Keystone is the case the blocked status exists for.
OPENSTACK_ERRORS = (
    openstack.exceptions.SDKException,
    keystoneauth1.exceptions.base.ClientException,
)

# A rule's identity is the value of these fields, in this order. OpenStack assigns the id,
# tenant, and description itself, and reports the rest back exactly as configured, so two
# rules with the same identity are the same rule.
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

    def __init__(self, provider_config: ProviderConfig) -> None:
        """Initialise the reconciler.

        Args:
            provider_config: The OpenStack credentials and region to reconcile in.
        """
        self._provider_config = provider_config

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
        try:
            # The SDK's signature is narrower than the keyword arguments a connection
            # accepts at runtime, so it is called through an opaque callable. Connection
            # closes itself on exit.
            connect = typing.cast(typing.Callable[..., typing.Any], openstack.connect)
            with connect(**self._auth_fields()) as connection:
                group = self._ensure_group(connection=connection, name=name)
                self._reconcile_rules(connection=connection, group=group, rules=rules)
                return str(group.id)
        except OPENSTACK_ERRORS as exc:
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
            # Oldest first. An absent timestamp reads as oldest, which is only ever a tie-break.
            key=lambda group: (str(group.created_at or ""), str(group.id)),
        )
        if not groups:
            logger.info("Creating security group %s", name)
            return connection.network.create_security_group(
                name=name, description=SECURITY_GROUP_DESCRIPTION
            )
        return self._keep_one_group(connection=connection, name=name, groups=groups)

    def _keep_one_group(
        self, connection: typing.Any, name: str, groups: list[typing.Any]
    ) -> typing.Any:
        """Pick the group to converge and delete the duplicates nothing is using.

        The survivor is the oldest group a port already attaches, or the oldest when none
        is, so two configurators racing to create one settle on the same group. A duplicate
        a port attaches is left in place and logged: OpenStack refuses that delete anyway.

        Args:
            connection: The authenticated OpenStack connection.
            name: The group name.
            groups: Every group of that name, oldest first.

        Returns:
            The security group this charm manages.
        """
        if len(groups) == 1:
            return groups[0]
        attached = {
            group.id: _ports_using(connection=connection, group_id=group.id) for group in groups
        }
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
            _delete_unused_group(connection=connection, group=group)
        return survivor

    def _reconcile_rules(
        self, connection: typing.Any, group: typing.Any, rules: list[SecurityGroupRule]
    ) -> None:
        """Add the configured rules, then remove the ones no longer configured.

        Additions come first so the group never loses a rule the runners may still be
        using — every runner of the scaleset carries this group. A rule the operator lists
        twice is added once.

        Args:
            connection: The authenticated OpenStack connection.
            group: The security group to converge.
            rules: The rules the group should hold.
        """
        observed = {
            tuple(getattr(rule, field, None) for field in RULE_FIELDS): rule
            for rule in connection.network.security_group_rules(security_group_id=group.id)
        }
        desired: set[tuple] = set()
        for rule in rules:
            identity = _get_identity(rule=rule)
            if identity in desired:
                continue
            desired.add(identity)
            if identity in observed:
                continue
            logger.info("Adding rule %s to security group %s", identity, group.name)
            connection.network.create_security_group_rule(
                security_group_id=group.id, **rule.neutron_fields
            )
        for identity, rule in observed.items():
            if identity in desired:
                continue
            logger.info("Removing rule %s from security group %s", identity, group.name)
            connection.network.delete_security_group_rule(security_group_rule=rule)


def _get_identity(rule: SecurityGroupRule) -> tuple:
    """Return a configured rule's identity: the value of RULE_FIELDS, in order."""
    return tuple(rule.neutron_fields.get(field) for field in RULE_FIELDS)


def _delete_unused_group(connection: typing.Any, group: typing.Any) -> None:
    """Delete a duplicate group, tolerating a port that attached it since the check.

    The port check above and this delete cannot be atomic, so OpenStack can still answer
    with a conflict. That is the same condition the check guards against, so it is logged
    rather than raised: a group a port uses must not block the reconcile. Every other
    failure — a refused permission, an unreachable API — still propagates.
    """
    try:
        connection.network.delete_security_group(security_group=group.id)
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


def _reason(exc: Exception) -> str:
    """Return the failure as one line, for the log."""
    return " ".join(str(exc).split()) or type(exc).__name__
