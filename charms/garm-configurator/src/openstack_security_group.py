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
# Seconds before an OpenStack request gives up; long enough for a busy Neutron, short enough
# that a firewalled endpoint blocks the unit rather than wedging the hook.
REQUEST_TIMEOUT_SECONDS = 30
SECURITY_GROUP_DESCRIPTION = (
    "Managed by the garm-configurator charm; its rules follow the security-group-rules option."
)

# What a reconcile can fail with: the SDK's own hierarchy for API responses, and
# keystoneauth's for transport and authentication, which never reach the SDK's base class —
# an unreachable Keystone is the case the blocked status exists for.
_OPENSTACK_ERRORS = (
    openstack.exceptions.SDKException,
    keystoneauth1.exceptions.base.ClientException,
)

# Neutron treats these as the same any-address rule (``securitygroups_db._rule_to_key``), and a
# new group already carries one egress rule per ethertype spelled this way. Comparing the
# literal strings would make every reconcile try to create them again and get a 409.
ANY_ADDRESS_PREFIXES = (None, "0.0.0.0/0", "::/0")

# The SDK resource names the ethertype ``ether_type``; the body it is created from spells it
# ``ethertype``. Reading the wrong one leaves it unset on every observed rule, which would
# make each configured rule look new and rewrite the whole group on every reconcile.
_SDK_ATTRIBUTE = {"ethertype": "ether_type"}

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
            with self._connection() as connection:
                group = self._ensure_group(connection=connection, name=name)
                self._reconcile_rules(connection=connection, group=group, rules=rules)
                return str(group.id)
        except _OPENSTACK_ERRORS as exc:
            raise SecurityGroupReconcileError(_reason(exc)) from exc

    def delete(self, name: str) -> bool:
        """Delete the managed group, unless a port still attaches it.

        Called when the operator turns the feature off and when the application is removed.

        Args:
            name: The group name, as returned by :func:`security_group_name`.

        Returns:
            Whether a group was deleted. This never raises: it runs while the charm is being
            removed, where a failure must not block the removal that asked for it.
        """
        try:
            with self._connection() as connection:
                deleted = False
                for group in self._groups_named(connection=connection, name=name):
                    deleted = _delete_group(connection=connection, group=group) or deleted
                return deleted
        except _OPENSTACK_ERRORS as exc:
            logger.warning("Could not delete security group %s: %s", name, _reason(exc))
            return False

    def _connection(self) -> typing.Any:
        """Return a connection authenticated with the provider config.

        The SDK's signature is narrower than the keyword arguments a connection accepts at
        runtime, so it is called through an opaque callable. Connection closes itself on exit.
        """
        connect = typing.cast(typing.Callable[..., typing.Any], openstack.connect)
        return connect(**self._auth_fields())

    def _auth_fields(self) -> dict[str, object]:
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
            # Without it a blackholed Keystone hangs the hook instead of blocking the unit.
            "api_timeout": REQUEST_TIMEOUT_SECONDS,
        }

    def _ensure_group(self, connection: typing.Any, name: str) -> typing.Any:
        """Return the named group, creating it when the project has none.

        Args:
            connection: The authenticated OpenStack connection.
            name: The group name.

        Returns:
            The security group this charm manages.
        """
        groups = self._groups_named(connection=connection, name=name)
        if not groups:
            logger.info("Creating security group %s", name)
            return connection.network.create_security_group(
                name=name, description=SECURITY_GROUP_DESCRIPTION
            )
        return self._keep_one_group(connection=connection, name=name, groups=groups)

    @staticmethod
    def _groups_named(connection: typing.Any, name: str) -> list[typing.Any]:
        """Return this project's groups of that name, oldest first.

        The name and project are filtered server-side: with admin-scoped credentials an
        unfiltered list returns every project's groups, and another project's group of the
        same name would count as a duplicate to delete.
        """
        return sorted(
            connection.network.security_groups(
                name=name, project_id=connection.current_project_id
            ),
            # An absent timestamp reads as oldest, which is only ever a tie-break.
            key=lambda group: (str(group.created_at or ""), str(group.id)),
        )

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
            _delete_group(connection=connection, group=group)
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
        observed: dict[tuple, typing.Any] = {}
        surplus: list[typing.Any] = []
        for rule in connection.network.security_group_rules(security_group_id=group.id):
            identity = _get_observed_identity(rule=rule)
            if identity in observed:
                # Neutron accepts the same rule twice; only one is wanted.
                surplus.append(rule)
                continue
            observed[identity] = rule

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
                security_group_id=group.id, **_neutron_fields(rule=rule)
            )

        obsolete = [rule for identity, rule in observed.items() if identity not in desired]
        for rule in obsolete + surplus:
            logger.info(
                "Removing rule %s from security group %s",
                _get_observed_identity(rule=rule),
                group.name,
            )
            connection.network.delete_security_group_rule(security_group_rule=rule)


def _get_observed_identity(rule: typing.Any) -> tuple:
    """Return the identity of a rule as the SDK reports it, `ether_type` included."""
    return tuple(
        _normalised(field=field, value=getattr(rule, _SDK_ATTRIBUTE.get(field, field), None))
        for field in RULE_FIELDS
    )


def _neutron_fields(rule: SecurityGroupRule) -> dict[str, object]:
    """Return a configured rule as OpenStack names its fields."""
    # Neutron defaults to IPv4; only an IPv6 prefix, which is the one with a colon, needs
    # saying. "any" is spelled as a null protocol and as no prefix at all.
    ethertype = "IPv6" if rule.remote_ip_prefix and ":" in rule.remote_ip_prefix else "IPv4"
    return {
        "direction": rule.direction,
        "ethertype": ethertype,
        "protocol": None if rule.protocol == "any" else rule.protocol,
        "port_range_min": rule.port_min,
        "port_range_max": rule.port_max,
        "remote_ip_prefix": _normalised(field="remote_ip_prefix", value=rule.remote_ip_prefix),
    }


def _normalised(field: str, value: object) -> object:
    """Return a rule value in the form Neutron compares it in."""
    if field == "remote_ip_prefix" and value in ANY_ADDRESS_PREFIXES:
        return None
    return value


def _get_identity(rule: SecurityGroupRule) -> tuple:
    """Return a configured rule's identity: the value of RULE_FIELDS, in order."""
    fields = _neutron_fields(rule=rule)
    return tuple(fields.get(field) for field in RULE_FIELDS)


def _delete_group(connection: typing.Any, group: typing.Any) -> bool:
    """Delete one group, treating the two refusals that are not this charm's as warnings.

    A conflict means a port still attaches the group, and a refusal means the credentials may
    not delete groups; either way the group stays, the caller carries on, and neither is worth
    stranding the unit or blocking an application removal over.

    Returns:
        Whether the group was deleted.
    """
    try:
        connection.network.delete_security_group(security_group=group.id)
        return True
    except openstack.exceptions.ConflictException:
        logger.warning(
            "Leaving security group %s (%s) in place: a port still attaches it",
            group.name,
            group.id,
        )
    except openstack.exceptions.ForbiddenException:
        logger.warning(
            "Could not delete security group %s (%s): the OpenStack credentials may not"
            " delete security groups. Leaving it in place",
            group.name,
            group.id,
        )
    return False


def _ports_using(connection: typing.Any, group_id: str) -> list[typing.Any]:
    """Return the ports that attach a security group.

    The SDK maps ``security_group_ids`` onto Neutron's ``security_groups`` filter, and the
    result is filtered again here so a server that ignores the filter cannot make every
    port in the project look attached.
    """
    return [
        port
        for port in connection.network.ports(security_group_ids=[group_id])
        if group_id in (port.security_group_ids or [])
    ]


def _reason(exc: Exception) -> str:
    """Return the failure as one line, for the log."""
    return " ".join(str(exc).split()) or type(exc).__name__
