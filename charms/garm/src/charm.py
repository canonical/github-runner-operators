#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import logging
import secrets
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


def render_garm_toml(
    *,
    listen_address: str,
    listen_port: int,
    db_path: str,
    jwt_secret: str,
) -> str:
    """Render GARM's TOML configuration file content.

    Args:
        listen_address: IP address for the GARM API server to bind on.
        listen_port: Port for the GARM API server.
        db_path: Filesystem path to the SQLite database file.
        jwt_secret: Secret string used to sign GARM JWT tokens.

    Returns:
        TOML-formatted string ready to be written to disk.
    """
    config: dict[str, typing.Any] = {
        "database": {
            "backend": "sqlite3",
            "sqlite3": {"db_file": db_path},
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
    }
    return tomli_w.dumps(config)


def _generate_garm_secrets() -> dict[str, str]:
    """Generate a fresh set of GARM secrets.

    Returns:
        Dict with key ``jwt-secret`` as a 64-char hex string.
    """
    return {
        "jwt-secret": secrets.token_hex(32),
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
        # TODO: Eliminate double-replan (ISD-5718). paas_charm calls replan()
        # internally in super().restart(), which starts GARM with the default
        # command momentarily before this method overrides it. Acceptable for
        # the scaffold; resolve by contributing an upstream hook in a future story.
        super().restart(rerun_migrations=rerun_migrations)
        container = self.unit.get_container(CONTAINER_NAME)
        try:
            self._push_garm_config(container)
        except ops.SecretNotFoundError:
            logger.warning("garm-secrets not yet available; deferring config push to next event")
            self.unit.status = ops.WaitingStatus("Waiting for leader to initialise garm-secrets")
            return
        container.add_layer(
            "garm-command",
            {
                "services": {
                    PEBBLE_SERVICE_NAME: {
                        "override": "merge",
                        "command": f"{GARM_BINARY} -config {GARM_CONFIG_PATH}",
                    }
                }
            },
            combine=True,
        )
        container.replan()

    def _ensure_secrets(self) -> None:
        """Create or refresh the garm-secrets Juju secret (leader only).

        On initial deploy the secret is created. On redeploy the existing
        secret is re-used; its content is left unchanged so GARM keeps the
        same JWT secret across restarts.
        """
        if not self.unit.is_leader():
            return
        try:
            self.model.get_secret(label=GARM_SECRETS_LABEL)
        except ops.SecretNotFoundError:
            self.app.add_secret(_generate_garm_secrets(), label=GARM_SECRETS_LABEL)

    def _get_jwt_secret(self) -> str:
        """Retrieve the JWT secret from the juju secret store.

        Returns:
            The jwt-secret string.
        """
        secret = self.model.get_secret(label=GARM_SECRETS_LABEL)
        return secret.get_content()["jwt-secret"]

    def _push_garm_config(self, container: ops.Container) -> None:
        """Render and push the GARM TOML config into the Pebble container.

        Args:
            container: The Pebble container to push the config into.
        """
        toml_content = render_garm_toml(
            listen_address=str(self.config.get("garm-listen-address", "0.0.0.0")),
            listen_port=int(self.config.get("garm-listen-port", 9997)),
            db_path=str(self.config.get("garm-db-path", "/etc/garm/garm.db")),
            jwt_secret=self._get_jwt_secret(),
        )
        container.push(GARM_CONFIG_PATH, toml_content, make_dirs=True)


if __name__ == "__main__":
    ops.main(GarmCharm)
