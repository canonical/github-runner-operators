#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import logging
import secrets
import string
import typing

import ops
import paas_charm.go
import tomli_w

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: typing.Final[str] = "/etc/garm/config.toml"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"

_DB_PASSPHRASE_LENGTH: typing.Final[int] = 32


def _generate_passphrase(length: int = _DB_PASSPHRASE_LENGTH) -> str:
    """Generate a random alphanumeric passphrase for GARM DB encryption.

    Args:
        length: Length of the passphrase (default 32 for AES-256).

    Returns:
        Random alphanumeric string of the given length.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def render_garm_toml(
    *,
    listen_address: str,
    listen_port: int,
    jwt_secret: str,
    db_passphrase: str,
    postgresql_config: dict[str, typing.Any],
) -> str:
    """Render GARM's TOML configuration file content.

    Args:
        listen_address: IP address for the GARM API server to bind on.
        listen_port: Port for the GARM API server.
        jwt_secret: Secret string used to sign GARM JWT tokens.
        db_passphrase: 32-character passphrase for AES-256 encryption of secrets in the DB.
        postgresql_config: PostgreSQL connection parameters (username, password,
            hostname, port, database, sslmode).

    Returns:
        TOML-formatted string ready to be written to disk.
    """
    config: dict[str, typing.Any] = {
        "database": {
            "backend": "postgresql",
            "passphrase": db_passphrase,
            "postgresql": postgresql_config,
        },
        "apiserver": {
            "bind": listen_address,
            "port": listen_port,
            "use_tls": False,
        },
        "jwt_auth": {
            "secret": jwt_secret,
            "time_to_live": "8760h",
        },
        "metrics": {
            "disable_auth": True,
            "enable": True,
        },
        "provider": [
            {
                "name": "openstack",
                "provider_type": "external",
                "description": "OpenStack provider",
                "external": {
                    "config_file": "",
                    "provider_executable": OPENSTACK_PROVIDER_BINARY,
                    "environment_variables": [],
                },
            }
        ],
    }
    return tomli_w.dumps(config)


def _generate_garm_secrets() -> dict[str, str]:
    """Generate a fresh set of GARM secrets.

    Returns:
        Dict with ``jwt-secret`` (64-char hex) and ``db-passphrase`` (32-char alnum).
    """
    return {
        "jwt-secret": secrets.token_hex(32),
        "db-passphrase": _generate_passphrase(),
    }


class GarmCharm(paas_charm.go.Charm):
    """GARM charm — manages the GARM service via Pebble."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the charm.

        Args:
            args: Passed through to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)

    def _on_install(self, _: ops.InstallEvent) -> None:
        """Ensure secrets exist on first install."""
        self._ensure_secrets()

    def restart(self, rerun_migrations: bool = False) -> None:
        """Write GARM config then restart the workload.

        Overrides the parent to inject the TOML config file and correct
        Pebble command before each restart.

        Args:
            rerun_migrations: Passed through to the parent restart.
        """
        if not self.is_ready():
            return
        self._ensure_secrets()

        # Short-circuit if postgresql relation data is not yet available.
        # GARM cannot start without a database connection.
        if not self._get_postgresql_config():
            logger.info("PostgreSQL relation data not yet available; blocking")
            self.unit.status = ops.BlockedStatus("Waiting for postgresql relation")
            return

        # TODO: Eliminate double-replan (ISD-5718). paas_charm calls replan()
        # internally in super().restart(), which starts GARM with the default
        # command momentarily before this method overrides it. Acceptable for
        # the scaffold; resolve by contributing an upstream hook in a future story.
        super().restart(rerun_migrations=rerun_migrations)
        container = self.unit.get_container(CONTAINER_NAME)
        try:
            self._push_garm_config(container)
        except ops.SecretNotFoundError:
            logger.warning("garm-secrets not yet available; deferring config push")
            self.unit.status = ops.WaitingStatus(
                "Waiting for leader to initialise garm-secrets"
            )
            return
        container.add_layer(
            "garm-command",
            {
                "services": {
                    PEBBLE_SERVICE_NAME: {
                        "override": "merge",
                        "startup": "enabled",
                        "command": f"{GARM_BINARY} -config {GARM_CONFIG_PATH}",
                    }
                }
            },
            combine=True,
        )
        container.replan()

    def _ensure_secrets(self) -> None:
        """Create the garm-secrets juju secret on first call (leader only)."""
        if not self.unit.is_leader():
            return
        try:
            self.model.get_secret(label=GARM_SECRETS_LABEL)
        except ops.SecretNotFoundError:
            self.app.add_secret(_generate_garm_secrets(), label=GARM_SECRETS_LABEL)

    def _get_secrets(self) -> dict[str, str]:
        """Retrieve secrets from the juju secret store.

        Returns:
            Dict with jwt-secret and db-passphrase.

        Raises:
            ops.SecretNotFoundError: If the secret doesn't exist yet.
        """
        secret = self.model.get_secret(label=GARM_SECRETS_LABEL)
        return secret.get_content()

    def _get_postgresql_config(self) -> dict[str, typing.Any] | None:
        """Get PostgreSQL config from relation data, or None if not available.

        Returns:
            Dict with postgresql connection parameters ready for the TOML config,
            or None if the relation data is not yet available.
        """
        pg_requirer = self._database_requirers.get("postgresql")
        if pg_requirer is None:
            return None

        relations = pg_requirer.fetch_relation_data()
        if not relations:
            return None

        for data in relations.values():
            if not data:
                continue
            endpoints = data.get("endpoints", "")
            if not endpoints:
                continue

            # GARM only supports a single hostname in its PostgreSQL config struct
            # (no multi-host DSN or failover list), so we take the first endpoint.
            host_port = endpoints.split(",")[0]
            host, port = host_port.rsplit(":", 1)

            return {
                "username": data.get("username", ""),
                "password": data.get("password", ""),
                "hostname": host,
                "port": int(port),
                "database": data.get("database", ""),
                "sslmode": "prefer",
            }

        return None

    def _push_garm_config(self, container: ops.Container) -> None:
        """Render and push the GARM TOML config into the Pebble container.

        Args:
            container: The Pebble container to push the config into.
        """
        postgresql_config = self._get_postgresql_config()
        if not postgresql_config:
            logger.info("PostgreSQL relation data not yet available")
            return

        secrets = self._get_secrets()
        logger.info(
            "Configuring GARM with PostgreSQL backend at %s:%s",
            postgresql_config["hostname"],
            postgresql_config["port"],
        )
        toml_content = render_garm_toml(
            listen_address=str(self.config.get("garm-listen-address", "0.0.0.0")),
            listen_port=int(self.config.get("garm-listen-port", 9997)),
            jwt_secret=secrets["jwt-secret"],
            db_passphrase=secrets["db-passphrase"],
            postgresql_config=postgresql_config,
        )
        container.push(GARM_CONFIG_PATH, toml_content, make_dirs=True)


if __name__ == "__main__":
    ops.main(GarmCharm)
