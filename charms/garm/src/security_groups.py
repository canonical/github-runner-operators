# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Reconcile the OpenStack security group each scale set's runners are attached to.

The configurator owns the policy: it validates ``security-group-rules`` and publishes them on
the relation. This module owns the lifecycle, because only the GARM charm knows when a scale
set and its runners are gone: it creates ``garm-<scale set>``, converges its rules to the
published list, hands the id to the provider through the scale set's ``security_groups`` extra
spec, and deletes groups nothing claims any more.

Nothing the charms provide needs an ingress rule. GARM's remote shell rides the agent's
connection, which the runner opens to ``agent_url``, and a ``debug-ssh`` session is an
outbound tmate client on the runner; both are traffic the runner originates.
"""

import logging
import time
import typing

import keystoneauth1.exceptions.base
import openstack
import openstack.exceptions

from charm_state import SecurityGroupRule

logger = logging.getLogger(__name__)

SECURITY_GROUP_NAME_PREFIX = "garm-"
# Seconds before an OpenStack request gives up; long enough for a busy Neutron, short enough
# that a firewalled endpoint does not wedge the hook.
REQUEST_TIMEOUT_SECONDS = 30
# Everything this charm creates is named after the scale set and described with this marker, so
# a sweep can tell its groups from another GARM application's in the same project.
SECURITY_GROUP_DESCRIPTION = "Managed by the {} charm."
# A group whose port is still being removed cannot be deleted yet. On the removal path, retry
# briefly: no later pass runs to try again.
REMOVAL_DELETE_ATTEMPTS = 3
REMOVAL_DELETE_SETTLE_SECONDS = 5

# What a reconcile can fail with: the SDK's own hierarchy for API responses, and keystoneauth's
# for transport and authentication, which never reach the SDK's base class.
_OPENSTACK_ERRORS = (
    openstack.exceptions.SDKException,
    keystoneauth1.exceptions.base.ClientException,
)

# The SDK resource names the ethertype ``ether_type``; the body it is created from spells it
# ``ethertype``. Reading the wrong one leaves it unset on every observed rule, which would make
# each configured rule look new and rewrite the whole group on every reconcile.
_SDK_ATTRIBUTE = {"ethertype": "ether_type"}

# Neutron treats these as the same any-address rule (``securitygroups_db._rule_to_key``), and a
# new group already carries one egress rule per ethertype spelled this way. Comparing the
# literal strings would make every reconcile try to create them again and get a 409.
ANY_ADDRESS_PREFIXES = (None, "0.0.0.0/0", "::/0")

# A rule's identity is the value of these fields, in this order. OpenStack assigns the id,
# tenant, and description itself, and reports the rest back exactly as configured, so two rules
# with the same identity are the same rule.
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
    """Raised when a scale set's security group could not be reconciled with OpenStack."""


def security_group_name(scaleset_name: str) -> str:
    """Return the OpenStack name of the security group managed for a scale set.

    Args:
        scaleset_name: The scale set name the configurator configured.

    Returns:
        The group name, derived from the scale set name alone so a scale set keeps its group
        across charm upgrades and reconciles.
    """
    return f"{SECURITY_GROUP_NAME_PREFIX}{scaleset_name}"


class SecurityGroupReconciler:
    """Creates, converges, and deletes the security groups of one OpenStack tenant."""

    def __init__(self, provider_config: dict[str, str], owner: str) -> None:
        """Initialise the reconciler.

        Args:
            provider_config: One configurator's OpenStack credentials and region.
            owner: This application's name, written into the group description so a sweep
                only removes groups it created.
        """
        self._provider_config = provider_config
        self._description = SECURITY_GROUP_DESCRIPTION.format(owner)

    def reconcile(self, rules: dict[str, list[SecurityGroupRule]]) -> dict[str, str]:
        """Ensure each scale set's group exists and holds its rules, and sweep the rest.

        Args:
            rules: Per scale set name, the rules its group should hold. A scale set absent from
                this mapping no longer exists, so its group is deleted.

        Returns:
            Per scale set name, the id of the group the provider should attach.

        Raises:
            SecurityGroupReconcileError: If OpenStack refused or could not be reached. The caller
                skips these scale sets rather than creating runners without isolation.
        """
        groups: dict[str, str] = {}
        try:
            connect = typing.cast(typing.Callable[..., typing.Any], openstack.connect)
            with connect(**self._auth_fields()) as connection:
                claimed, duplicates = self._groups_by_name(connection=connection)
                for name, group_rules in rules.items():
                    group = claimed.pop(security_group_name(scaleset_name=name), None)
                    if group is None:
                        group = self._create_group(connection=connection, name=name)
                    self._reconcile_rules(connection=connection, group=group, rules=group_rules)
                    groups[name] = str(group.id)
                self._delete_unclaimed(
                    connection=connection, unclaimed=[*claimed.values(), *duplicates]
                )
        except _OPENSTACK_ERRORS as exc:
            raise SecurityGroupReconcileError(_reason(exc)) from exc
        return groups

    def delete(self) -> bool:
        """Delete every group this application created, unless a port still attaches it.

        Used when the application is removed.

        Returns:
            Whether any group was deleted. This never raises: it runs while the charm is being
            removed, where a failure must not block the removal.
        """
        try:
            connect = typing.cast(typing.Callable[..., typing.Any], openstack.connect)
            with connect(**self._auth_fields()) as connection:
                claimed, duplicates = self._groups_by_name(connection=connection)
                unclaimed = [*claimed.values(), *duplicates]
                return self._delete_unclaimed(connection=connection, unclaimed=unclaimed) > 0
        except _OPENSTACK_ERRORS as exc:
            logger.warning("Could not delete the managed security groups: %s", _reason(exc))
            return False

    def _auth_fields(self) -> dict[str, object]:
        """Return the keyword arguments the OpenStack SDK authenticates with."""
        config = self._provider_config
        return {
            "auth_url": config["auth_url"],
            "username": config["username"],
            "password": config["password"],
            "project_name": config["project_name"],
            "user_domain_name": config["user_domain_name"],
            "project_domain_name": config["project_domain_name"],
            "region_name": config["region_name"],
            "api_timeout": REQUEST_TIMEOUT_SECONDS,
        }

    def _groups_by_name(
        self, connection: typing.Any
    ) -> tuple[dict[str, typing.Any], list[typing.Any]]:
        """Return the groups this application created, keyed by name, plus any duplicates.

        The project is filtered server-side, and the name prefix and description marker
        client-side: another GARM application sharing the project owns its own groups.

        A duplicate sharing a name is returned separately rather than dropped, because a group
        that is never claimed is also never deleted.
        """
        groups: dict[str, typing.Any] = {}
        duplicates: list[typing.Any] = []
        for group in connection.network.security_groups(project_id=connection.current_project_id):
            if not (group.name or "").startswith(SECURITY_GROUP_NAME_PREFIX):
                continue
            if group.description != self._description:
                continue
            if group.name in groups:
                duplicates.append(group)
                continue
            groups[group.name] = group
        return groups, duplicates

    def _create_group(self, connection: typing.Any, name: str) -> typing.Any:
        """Create a scale set's group and return it."""
        logger.info("Creating security group %s", security_group_name(scaleset_name=name))
        return connection.network.create_security_group(
            name=security_group_name(scaleset_name=name), description=self._description
        )

    def _reconcile_rules(
        self, connection: typing.Any, group: typing.Any, rules: list[SecurityGroupRule]
    ) -> None:
        """Converge a group's rules to *rules*, which is authoritative.

        A rule listed twice is created once; a duplicate Neutron already holds is removed.

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
                surplus.append(rule)
                continue
            observed[identity] = rule

        desired = {_get_identity(rule=rule) for rule in rules}

        # Removals first: identity is the rule, so an obsolete rule can never stand in for one
        # being added, and adding first would leave the group briefly wider than the policy.
        obsolete = [rule for identity, rule in observed.items() if identity not in desired]
        for rule in obsolete + surplus:
            logger.info(
                "Removing rule %s from security group %s",
                _get_observed_identity(rule=rule),
                group.name,
            )
            connection.network.delete_security_group_rule(security_group_rule=rule)

        added: set[tuple] = set()
        for rule in rules:
            identity = _get_identity(rule=rule)
            if identity in observed or identity in added:
                continue
            added.add(identity)
            logger.info("Adding rule %s to security group %s", identity, group.name)
            connection.network.create_security_group_rule(
                security_group_id=group.id, **_neutron_fields(rule=rule)
            )

    def _delete_unclaimed(
        self,
        connection: typing.Any,
        unclaimed: typing.Iterable[typing.Any],
        settle_attempts: int = 1,
    ) -> int:
        """Delete groups no scale set claims, one refusal at a time.

        Args:
            connection: The authenticated OpenStack connection.
            unclaimed: The groups to remove.
            settle_attempts: How many times to retry a group a port still attaches. One on the
                reconcile path, which runs again anyway; more on the removal path, which does not.

        Returns:
            How many groups were deleted.
        """
        deleted = 0
        for group in unclaimed:
            for attempt in range(1, settle_attempts + 1):
                last = attempt == settle_attempts
                if self._delete_group(connection=connection, group=group, last=last):
                    deleted += 1
                    break
                if not last:
                    time.sleep(REMOVAL_DELETE_SETTLE_SECONDS)
        return deleted

    def _delete_group(self, connection: typing.Any, group: typing.Any, last: bool) -> bool:
        """Delete one group, reporting the refusals that are not this charm's as logs.

        Args:
            connection: The authenticated OpenStack connection.
            group: The group to delete.
            last: Whether this is the final attempt, so a port still attached is worth reporting.

        Returns:
            Whether the group is gone.
        """
        try:
            connection.network.delete_security_group(security_group=group.id)
            logger.info("Deleted security group %s (%s)", group.name, group.id)
            return True
        except openstack.exceptions.NotFoundException:
            # A concurrent pass deleted it, which is the outcome this call wanted.
            logger.info("Security group %s is already gone", group.name)
            return True
        except openstack.exceptions.ConflictException:
            # Expected for hours after a scale set is deleted: Nova removes the port
            # asynchronously, and until it does the group is still attached.
            if last:
                logger.info("Keeping security group %s: a port still attaches it", group.name)
            return False
        except openstack.exceptions.ForbiddenException:
            logger.warning(
                "Could not delete security group %s: the OpenStack credentials may not"
                " delete security groups",
                group.name,
            )
            return False


def _get_identity(rule: SecurityGroupRule) -> tuple:
    """Return a configured rule's identity: the value of RULE_FIELDS, in order."""
    fields = _neutron_fields(rule=rule)
    return tuple(fields.get(field) for field in RULE_FIELDS)


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


def _reason(exc: Exception) -> str:
    """Return the failure as one line."""
    return " ".join(str(exc).split()) or type(exc).__name__
