#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import dataclasses
import logging
import secrets
import string
import typing

import ops
import paas_charm.go
import tomli_w
from paas_charm.app import WorkloadConfig

from garm_api import GarmApiClient, GarmApiError

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: typing.Final[str] = "/etc/garm/config.toml"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
GARM_ADMIN_CREDENTIALS_LABEL: typing.Final[str] = "garm-admin-credentials"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_PORT: typing.Final[int] = 8080

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
    listen_port: int,
    jwt_secret: str,
    db_passphrase: str,
    postgresql_config: dict[str, typing.Any],
) -> str:
    """Render GARM's TOML configuration file content.

    Args:
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
            "bind": "0.0.0.0",
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


def _generate_admin_password() -> str:
    """Generate a random password satisfying GARM's strong-password policy.

    Policy: min 12 chars, at least one uppercase, one lowercase, one digit,
    one symbol.  Full entropy is distributed across all 20 positions via a
    Fisher-Yates shuffle so the structure is not predictable from the source.

    Returns:
        A 20-character password guaranteed to meet GARM's requirements.
    """
    _SYMBOLS = "!@#$%-_=+"
    alphabet = string.ascii_letters + string.digits + _SYMBOLS
    mandatory = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_SYMBOLS),
    ]
    filler = [secrets.choice(alphabet) for _ in range(16)]
    chars = mandatory + filler
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


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

    @property
<<<<<<< HEAD
    def _listen_port(self) -> int:
        """GARM API listen port from charm config."""
        return int(self.config.get("garm-listen-port", 9997))
=======
    def _workload_config(self) -> WorkloadConfig:
        """Pin GARM to a fixed port and disable the default metrics scrape job.

        GARM serves its API and /metrics on a single fixed port (GARM_PORT);
        the framework's app-port is unsupported, so we force the workload port
        (used for ingress, opened ports, and the service URL) to GARM_PORT
        rather than reading app-port. The scrape target is declared in
        paas-config.yaml, so metrics_target is set to None to suppress the
        framework's default metrics-port scrape job.
        """
        return dataclasses.replace(super()._workload_config, port=GARM_PORT, metrics_target=None)
>>>>>>> origin/main

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

        # GARM serves its API and metrics on the same fixed port (GARM_PORT) — it has
        # no separate metrics listener — and declares its scrape target in
        # paas-config.yaml, so the go-framework's app-port/metrics-port/metrics-path
        # settings don't apply. _workload_config also pins the workload port to
        # GARM_PORT, so app-port has no effect on ingress, the opened ports, or the
        # service URL (they can't drift from GARM's actual port). Warn rather than
        # block when an operator sets any to a non-default value, tolerating their
        # absence (the framework may drop them in future).
        for option, default in (
            ("app-port", GARM_PORT),
            ("metrics-port", GARM_PORT),
            ("metrics-path", "/metrics"),
        ):
            value = self.config.get(option)
            if value is not None and str(value) != str(default):
                logger.warning(
                    "%s=%s is not supported and has no effect; GARM serves on port %d and "
                    "declares its Prometheus scrape config in paas-config.yaml",
                    option,
                    value,
                    GARM_PORT,
                )

        # Short-circuit if postgresql relation data is not yet available.
        # GARM cannot start without a database connection.
        pg_config = self._get_postgresql_config()
        if not pg_config:
            logger.info("PostgreSQL relation data not yet available; blocking")
            self.unit.status = ops.BlockedStatus("Waiting for postgresql relation")
            return

        container = self.unit.get_container(CONTAINER_NAME)

        # Push the TOML config and set the command layer BEFORE calling
        # super().restart() so that GARM never starts with a missing config file.
        # If secrets are unavailable we return early before touching the service.
        try:
            self._push_garm_config(container, pg_config)
        except ops.SecretNotFoundError:
            logger.warning("garm-secrets not yet available; deferring config push")
            self.unit.status = ops.WaitingStatus("Waiting for leader to initialise garm-secrets")
            return

        # TODO: Eliminate double-replan (ISD-5718). On first deployment, paas_charm
        # adds its Pebble layer inside super().restart() at a higher stack position
        # than "garm-command", temporarily overriding the command. The add_layer +
        # replan below re-establishes the correct command. On subsequent restarts
        # "garm-command" is already above the paas_charm layer so that replan is a
        # no-op. Fix properly by contributing an upstream hook to paas_charm.
        super().restart(rerun_migrations=rerun_migrations)
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
        self._maybe_first_run()

    def _ensure_secrets(self) -> None:
        """Create garm-secrets and garm-admin-credentials juju secrets (leader only)."""
        if not self.unit.is_leader():
            return
        try:
            self.model.get_secret(label=GARM_SECRETS_LABEL)
        except ops.SecretNotFoundError:
            self.app.add_secret(_generate_garm_secrets(), label=GARM_SECRETS_LABEL)
        try:
            self.model.get_secret(label=GARM_ADMIN_CREDENTIALS_LABEL)
        except ops.SecretNotFoundError:
            self.app.add_secret(
                {
                    "username": "admin",
                    "password": _generate_admin_password(),
                    "email": "admin@garm.local",
                    "full-name": "GARM Admin",
                },
                label=GARM_ADMIN_CREDENTIALS_LABEL,
            )
            logger.info(
                "GARM admin credentials stored in Juju secret '%s'."
                " Retrieve with: juju secret-get --label %s",
                GARM_ADMIN_CREDENTIALS_LABEL,
                GARM_ADMIN_CREDENTIALS_LABEL,
            )

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

    def _get_admin_credentials(self) -> dict[str, str] | None:
        """Retrieve the GARM admin credentials from the Juju secret store.

        Returns:
            Dict with ``username``, ``password``, ``email``, ``full-name``,
            or None if the secret is not yet available.
        """
        try:
            secret = self.model.get_secret(label=GARM_ADMIN_CREDENTIALS_LABEL)
            return secret.get_content()
        except ops.SecretNotFoundError:
            return None

    def _maybe_first_run(self) -> None:
        """Call GARM first-run initialisation if GARM is not yet initialised."""
        if not self.unit.is_leader():
            return
        admin_creds = self._get_admin_credentials()
        if not admin_creds:
            logger.warning("Admin credentials secret not yet available; skipping first-run check")
            return

        try:
            username = admin_creds["username"]
            password = admin_creds["password"]
            email = admin_creds["email"]
            full_name = admin_creds["full-name"]
        except KeyError as exc:
            logger.error(
                "Admin credentials secret is missing required key %s; cannot initialise GARM",
                exc,
            )
            return

        # Always connect via loopback. If the operator has configured a specific
        # non-wildcard listen address, use that instead (0.0.0.0 and :: bind all
        # interfaces including loopback so 127.0.0.1 always works for those).
        listen_address = str(self.config.get("garm-listen-address", "0.0.0.0"))
        api_address = "127.0.0.1" if listen_address in ("0.0.0.0", "::") else listen_address
        api_host = f"[{api_address}]" if ":" in api_address and not api_address.startswith("[") else api_address
        base_url = f"http://{api_host}:{self._listen_port}/api/v1"
        client = GarmApiClient(base_url)

        try:
            if client.is_initialized():
                return
            logger.info("GARM not yet initialised; running first-run setup")
            client.first_run(
                username=username,
                password=password,
                email=email,
                full_name=full_name,
            )
        except GarmApiError as exc:
            logger.warning("GARM first-run check failed (will retry on next event): %s", exc)

    def _push_garm_config(
        self,
        container: ops.Container,
        postgresql_config: dict[str, typing.Any] | None = None,
    ) -> None:
        """Render and push the GARM TOML config into the Pebble container.

        Args:
            container: The Pebble container to push the config into.
            postgresql_config: Pre-fetched PostgreSQL connection parameters.
                If None, fetches from the relation data (adds a round-trip).
        """
        if postgresql_config is None:
            postgresql_config = self._get_postgresql_config()
        if not postgresql_config:
            logger.info("PostgreSQL relation data not yet available")
            return

        garm_secrets = self._get_secrets()
        logger.info(
            "Configuring GARM with PostgreSQL backend at %s:%s",
            postgresql_config["hostname"],
            postgresql_config["port"],
        )
        toml_content = render_garm_toml(
<<<<<<< HEAD
            listen_address=str(self.config.get("garm-listen-address", "0.0.0.0")),
            listen_port=self._listen_port,
            jwt_secret=garm_secrets["jwt-secret"],
            db_passphrase=garm_secrets["db-passphrase"],
=======
            listen_port=GARM_PORT,
            jwt_secret=secrets["jwt-secret"],
            db_passphrase=secrets["db-passphrase"],
>>>>>>> origin/main
            postgresql_config=postgresql_config,
        )
        container.push(GARM_CONFIG_PATH, toml_content, make_dirs=True)


if __name__ == "__main__":
    ops.main(GarmCharm)
