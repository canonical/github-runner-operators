# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm state parsing for the GARM charm."""

import dataclasses
import logging
import typing

import ops

logger = logging.getLogger(__name__)

DEBUG_SSH_INTEGRATION_NAME: typing.Final[str] = "debug-ssh"


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


@dataclasses.dataclass(frozen=True)
class GarmConfig:
    """Charm-level GARM configuration parsed from the Juju model.

    Attributes:
        use_runner_proxy_for_tmate: Whether to route tmate traffic through the runner proxy.
    """

    use_runner_proxy_for_tmate: bool

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "GarmConfig":
        """Parse GARM config from charm config options.

        Args:
            charm: The charm instance.

        Returns:
            Parsed GarmConfig.
        """
        return cls(
            use_runner_proxy_for_tmate=bool(
                charm.config.get("use-runner-proxy-for-tmate", False)
            ),
        )


def _get_ssh_debug_connections(charm: ops.CharmBase) -> list[SSHDebugInfo]:
    """Read SSH debug connection info from the debug-ssh relation.

    Args:
        charm: The charm instance.

    Returns:
        List of SSHDebugInfo for units that have sent complete relation data.
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

        if not host or not port_str or not rsa_fingerprint or not ed25519_fingerprint:
            logger.warning(
                "%s relation data for %s not yet ready.",
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

    return connections


@dataclasses.dataclass(frozen=True)
class CharmState:
    """Consolidated charm state for the GARM charm.

    Attributes:
        ssh_debug_connections: SSH debug connection info from the debug-ssh relation.
        garm_config: GARM-specific charm configuration.
    """

    ssh_debug_connections: list[SSHDebugInfo]
    garm_config: GarmConfig

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
            garm_config=GarmConfig.from_charm(charm),
        )
