# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm state parsing for the GARM charm.

Builds the desired GARM org/repo entities from the garm-configurator relation and the SSH
debug connections from the debug-ssh relation into a ``CharmState`` value (via
``CharmState.from_charm``), keeping that relation-parsing out of ``charm.py``. Credential and
scaleset specs are still built in ``charm.py`` today; they can move here under the same pattern
as the state grows.
"""

import dataclasses
import logging
import typing
from collections.abc import Mapping

import ops

from entity_reconciler import EntitySpec

logger = logging.getLogger(__name__)

DEBUG_SSH_INTEGRATION_NAME: typing.Final[str] = "debug-ssh"
GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"


@dataclasses.dataclass(frozen=True)
class SSHDebugInfo:
    """SSH debug connection information from the debug-ssh relation.

    Attributes:
        host: The tmate server hostname or IP.
        port: The tmate server port.
        rsa_fingerprint: RSA fingerprint of the tmate server.
        ed25519_fingerprint: Ed25519 fingerprint of the tmate server.
    """

    host: str
    port: int
    rsa_fingerprint: str
    ed25519_fingerprint: str


# Databag keys written by the garm-configurator charm — the single source of
# truth for the configurator→garm relation contract for runner options.
RUNNER_OPTION_DATABAG_KEYS: typing.Final = (
    "dockerhub_mirror",
    "runner_http_proxy",
    "aproxy_exclude_addresses",
    "aproxy_redirect_ports",
    "otel_collector_endpoint",
    "pre_job_script",
)


@dataclasses.dataclass(frozen=True)
class RunnerConfig:
    """Runner-behaviour options sourced from the garm-configurator relation.

    Every field is a plain string; an empty string means "unset". Values are
    validated upstream by the configurator charm, so consuming them here (and in
    the template renderer) is purely mechanical.

    Attributes:
        dockerhub_mirror: Docker registry mirror URL, or "".
        runner_http_proxy: Upstream HTTP proxy that aproxy forwards to, or "".
        aproxy_exclude_addresses: Comma-separated addresses/CIDRs to bypass, or "".
        aproxy_redirect_ports: Comma-separated ports / N-M ranges to redirect, or "".
        otel_collector_endpoint: OTEL exporter endpoint, or "".
        pre_job_script: Operator bash appended to the pre-job hook, or "".
    """

    dockerhub_mirror: str = ""
    runner_http_proxy: str = ""
    aproxy_exclude_addresses: str = ""
    aproxy_redirect_ports: str = ""
    otel_collector_endpoint: str = ""
    pre_job_script: str = ""

    @classmethod
    def from_databag(cls, data: Mapping[str, str]) -> "RunnerConfig":
        """Build a config from a relation databag, ignoring missing keys.

        Args:
            data: The relation unit databag (or any mapping).

        Returns:
            A RunnerConfig with each field taken from its databag key, "" if absent.
        """
        return cls(**{key: (data.get(key) or "").strip() for key in RUNNER_OPTION_DATABAG_KEYS})

    def has_config(self) -> bool:
        """Whether any runner option is set (i.e. a custom template is needed).

        Returns:
            True if at least one field is non-empty.
        """
        return any(getattr(self, key) for key in RUNNER_OPTION_DATABAG_KEYS)


def credential_name(app_id: int, installation_id: int) -> str:
    """Return the GARM credential name for a GitHub App installation.

    The org/repo entity reconciler binds entities to credentials by this name, so both the
    credential and entity builders must derive it identically.
    """
    return f"app-{app_id}-{installation_id}"


def _get_ssh_debug_connections(charm: ops.CharmBase) -> list[SSHDebugInfo]:
    """Read SSH debug connection info from the debug-ssh relation.

    Args:
        charm: The charm instance.

    Returns:
        List of SSHDebugInfo for units that have sent complete relation data,
        sorted by (host, port) for stable ordering across events.
    """
    relation = charm.model.get_relation(DEBUG_SSH_INTEGRATION_NAME)
    if relation is None:
        return []

    connections: list[SSHDebugInfo] = []
    for unit in relation.units:
        data = relation.data[unit]
        host = data.get("host")
        port_str = data.get("port")
        rsa_fingerprint = data.get("rsa_fingerprint")
        ed25519_fingerprint = data.get("ed25519_fingerprint")

        if not (host and port_str and rsa_fingerprint and ed25519_fingerprint):
            logger.warning(
                "%s relation data for %s not yet ready.",
                DEBUG_SSH_INTEGRATION_NAME,
                unit.name,
            )
            continue

        if any("\n" in v for v in (host, rsa_fingerprint, ed25519_fingerprint)):
            logger.warning(
                "Rejecting %s relation data for %s: value contains newline (possible injection).",
                DEBUG_SSH_INTEGRATION_NAME,
                unit.name,
            )
            continue

        try:
            port = int(port_str)
        except ValueError:
            logger.warning(
                "Invalid port '%s' in %s relation data for %s.",
                port_str,
                DEBUG_SSH_INTEGRATION_NAME,
                unit.name,
            )
            continue

        connections.append(
            SSHDebugInfo(
                host=host,
                port=port,
                rsa_fingerprint=rsa_fingerprint,
                ed25519_fingerprint=ed25519_fingerprint,
            )
        )

    # relation.units is unordered; sort so that ≥2 debug-ssh units always
    # produce the same connections[0] selection rather than flip-flopping.
    return sorted(connections, key=lambda c: (c.host, c.port))


def _get_desired_entities(charm: ops.CharmBase) -> list[EntitySpec]:
    """Build the desired GARM org/repo entities from configurator relation data.

    Each entity is bound to the GitHub App credential the github reconciler creates for the same
    configurator unit (``app-<app_id>-<installation_id>``). A unit naming an org or repo but
    lacking the App ids is skipped — its credential name cannot be derived.

    Args:
        charm: The charm instance.

    Returns:
        The full desired set of entity specs.
    """
    entities: dict[tuple[str, str], EntitySpec] = {}
    # Iterate relations and units in a stable order so the "keep the first" tie-break below is
    # deterministic: relation.units is an unordered set, so without sorting two units naming the
    # same entity with different credentials would flip-flop across reconciles.
    relations = sorted(
        charm.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []), key=lambda r: r.id
    )
    for relation in relations:
        for unit in sorted(relation.units, key=lambda unit: unit.name):
            data = relation.data[unit]
            org = data.get("org", "")
            repo = data.get("repo", "")
            if org:
                entity_type, entity_name = "organization", org
            elif repo:
                entity_type, entity_name = "repository", repo
            else:
                continue

            app_id_raw = data.get("github_app_id", "")
            installation_id_raw = data.get("github_installation_id", "")
            # Skip quietly while the App ids are merely absent (the configurator publishes the
            # entity name before them during bring-up); warn only on malformed values.
            if not (app_id_raw and installation_id_raw):
                continue
            try:
                app_id = int(app_id_raw)
                installation_id = int(installation_id_raw)
            except ValueError:
                logger.warning(
                    "Skipping entity %s from %s: non-numeric app/installation id "
                    "(app_id=%r, installation_id=%r)",
                    entity_name,
                    unit.name,
                    app_id_raw,
                    installation_id_raw,
                )
                continue

            # Dedupe by (type, name) so an org and a repo sharing a raw name don't collide. Keep
            # the first spec seen (iteration is ordered above) and warn if a later one derives a
            # different credential.
            key = (entity_type, entity_name)
            credentials_name = credential_name(app_id, installation_id)
            existing = entities.get(key)
            if existing is not None:
                if existing.credentials_name != credentials_name:
                    logger.warning(
                        "Conflicting credential for %s '%s' (%s vs %s); keeping the first",
                        entity_type,
                        entity_name,
                        existing.credentials_name,
                        credentials_name,
                    )
                continue
            entities[key] = EntitySpec(
                entity_type=entity_type,
                entity_name=entity_name,
                credentials_name=credentials_name,
            )
    return list(entities.values())


@dataclasses.dataclass(frozen=True)
class CharmState:
    """Consolidated charm state for the GARM charm.

    Attributes:
        ssh_debug_connections: SSH debug connection info from the debug-ssh relation.
        desired_entities: GARM org/repo entities derived from the garm-configurator relation.
    """

    ssh_debug_connections: list[SSHDebugInfo]
    desired_entities: list[EntitySpec]

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "CharmState":
        """Build CharmState from the current charm instance.

        Args:
            charm: The charm instance.

        Returns:
            Current CharmState.
        """
        return cls(
            ssh_debug_connections=_get_ssh_debug_connections(charm),
            desired_entities=_get_desired_entities(charm),
        )
