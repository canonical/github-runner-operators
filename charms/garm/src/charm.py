#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import dataclasses
import json
import logging
import secrets as _secrets
import string
import typing

import ops
import paas_charm.go
import tomli_w
from paas_charm.app import WorkloadConfig

from garm_api import GarmApiError, GarmClient
from runner_template import RunnerConfig
from scaleset_reconciler import ScalesetReconciler, ScalesetSpec

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: typing.Final[str] = "/etc/garm/config.toml"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_PORT: typing.Final[int] = 8080
GARM_ADMIN_EMAIL: typing.Final[str] = "admin@garm.local"
GARM_ADMIN_FULL_NAME: typing.Final[str] = "GARM Admin"

_DB_PASSPHRASE_LENGTH: typing.Final[int] = 32


def _generate_passphrase(length: int = _DB_PASSPHRASE_LENGTH) -> str:
    """Generate a random alphanumeric passphrase for GARM DB encryption.

    Args:
        length: Length of the passphrase (default 32 for AES-256).

    Returns:
        Random alphanumeric string of the given length.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(_secrets.choice(alphabet) for _ in range(length))


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
        "jwt-secret": _secrets.token_hex(32),
        "db-passphrase": _generate_passphrase(),
        "admin-username": "admin",
        "admin-password": f"Admin-{_secrets.token_hex(8)}-Gx1!",
    }


def _parse_pre_install_scripts(raw: str) -> dict[str, str]:
    """Parse pre_install_scripts from JSON relation data string."""
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except (ValueError, json.JSONDecodeError):
        pass
    return {}


class GarmCharm(paas_charm.go.Charm):
    """GARM charm — manages the GARM service via Pebble."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the charm.

        Args:
            args: Passed through to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_changed,
            self._on_configurator_changed,
        )
        self.framework.observe(
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_departed,
            self._on_configurator_changed,
        )

    def _on_install(self, _: ops.InstallEvent) -> None:
        """Ensure secrets exist on first install."""
        self._ensure_secrets()

    def _on_update_status(self, _: ops.HookEvent) -> None:
        """Retry GARM admin first-run until it succeeds."""
        self._maybe_first_run()

    @property
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

    def _on_configurator_changed(self, _: typing.Any) -> None:
        """Handle garm-configurator relation changes."""
        self._reconcile_scalesets()

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
            self.unit.status = ops.WaitingStatus("Waiting for leader to initialise garm-secrets")
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
        self._maybe_first_run()

    def _maybe_first_run(self) -> None:
        """Register the GARM admin user if it does not exist yet (leader only).

        GARM needs an initial admin (POST /first-run) before its API accepts
        authenticated calls. We log in first: if that succeeds GARM is already
        initialised and we do nothing, which avoids calling /first-run (and the
        409s it logs) on every update-status tick. Only when login fails do we
        attempt first-run, so the call also self-heals if GARM's database is ever
        reset. Failures (e.g. GARM not yet accepting connections after a restart)
        are logged and retried on the next event.
        """
        if not self.unit.is_leader():
            return
        secret = self._get_garm_secrets()
        if secret is None:
            return
        content = secret.get_content(refresh=True)
        admin_username = content.get("admin-username")
        admin_password = content.get("admin-password")
        if not admin_username or not admin_password:
            return
        client = GarmClient(f"{self._get_garm_url()}/api/v1")
        try:
            client.login(admin_username, admin_password)
            return
        except GarmApiError:
            logger.info("GARM admin login failed; attempting first-run initialisation")
        try:
            client.first_run(
                admin_username, admin_password, GARM_ADMIN_EMAIL, GARM_ADMIN_FULL_NAME
            )
        except GarmApiError as exc:
            logger.info("GARM first-run not completed yet (will retry): %s", exc)

    def _ensure_secrets(self) -> None:
        """Create the garm-secrets juju secret on first call (leader only)."""
        if not self.unit.is_leader():
            return
        secret = self._get_garm_secrets()
        if secret is None:
            self.app.add_secret(_generate_garm_secrets(), label=GARM_SECRETS_LABEL)
            return

        secret_content = secret.get_content(refresh=True)
        missing_secret_content = {}
        if "admin-username" not in secret_content:
            missing_secret_content["admin-username"] = "admin"
        if "admin-password" not in secret_content:
            missing_secret_content["admin-password"] = f"Admin-{_secrets.token_hex(8)}-Gx1!"
        if missing_secret_content:
            secret.set_content({**secret_content, **missing_secret_content})

    def _get_garm_secrets(self) -> ops.Secret | None:
        """Return the GARM secret object when available."""
        try:
            return self.model.get_secret(label=GARM_SECRETS_LABEL)
        except ops.SecretNotFoundError:
            return None

    def _get_secrets(self) -> dict[str, str]:
        """Retrieve secrets from the juju secret store.

        Returns:
            Dict with jwt-secret and db-passphrase.

        Raises:
            ops.SecretNotFoundError: If the secret doesn't exist yet.
        """
        secret = self.model.get_secret(label=GARM_SECRETS_LABEL)
        return secret.get_content()

    def _get_garm_url(self) -> str:
        """Return the local GARM API URL.

        GARM binds its API to the fixed port in-pod (see render_garm_toml), so
        the charm always reaches it over loopback.
        """
        return f"http://127.0.0.1:{GARM_PORT}"

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

    def _build_desired_scalesets(self) -> list[ScalesetSpec]:
        """Build the desired scaleset list from all garm-configurator relation units."""
        specs = []
        for relation in self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []):
            for unit in relation.units:
                data = relation.data[unit]
                name = data.get("name", "")
                if not name:
                    continue
                try:
                    min_idle = int(data.get("min_idle_runner", "0"))
                    max_runners = int(data.get("max_runner", "5"))
                except ValueError:
                    continue
                specs.append(
                    ScalesetSpec(
                        name=name,
                        provider_name=data.get("provider_name", ""),
                        credentials_name=data.get("credentials_name", ""),
                        image_id=data.get("image_id", ""),
                        flavor=data.get("flavor", ""),
                        os_arch=data.get("os_arch", "x64"),
                        min_idle_runners=min_idle,
                        max_runners=max_runners,
                        labels=[
                            label.strip()
                            for label in data.get("labels", "").split(",")
                            if label.strip()
                        ],
                        runner_group=data.get("runner_group", "default"),
                        pre_install_scripts=_parse_pre_install_scripts(
                            data.get("pre_install_scripts", "")
                        ),
                        runner_config=RunnerConfig.from_databag(data),
                    )
                )
        return specs

    def _reconcile_scalesets(self) -> None:
        """Sync GARM scalesets against garm-configurator relation data."""
        # Ensure the GARM admin exists before we attempt to authenticate below.
        self._maybe_first_run()
        secret = self._get_garm_secrets()
        if not secret:
            logger.warning("GARM secrets not yet available; deferring scaleset reconcile")
            return

        secret_content = secret.get_content(refresh=True)
        admin_username = secret_content.get("admin-username", "admin")
        admin_password = secret_content.get("admin-password", "")
        if not admin_password:
            logger.warning("admin-password not in GARM secrets; deferring scaleset reconcile")
            return

        garm_url = self._get_garm_url()
        if not garm_url:
            logger.warning("GARM URL not yet available; deferring scaleset reconcile")
            return

        try:
            client = GarmClient(f"{garm_url}/api/v1")
            client.token = client.login(admin_username, admin_password)
            desired = self._build_desired_scalesets()
            reconciler = ScalesetReconciler(client)
            reconciler.reconcile(desired)
        except GarmApiError as exc:
            logger.warning("GARM API error during scaleset reconcile: %s", exc)

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
            listen_port=GARM_PORT,
            jwt_secret=secrets["jwt-secret"],
            db_passphrase=secrets["db-passphrase"],
            postgresql_config=postgresql_config,
        )
        container.push(GARM_CONFIG_PATH, toml_content, make_dirs=True)


if __name__ == "__main__":
    ops.main(GarmCharm)
