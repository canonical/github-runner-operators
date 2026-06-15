#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import hashlib
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
TOML_HASH_LABEL: typing.Final[str] = "garm-toml-hash"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"

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


def _build_provider_list(
    providers: list[dict[str, str]] | None,
) -> list[dict[str, typing.Any]]:
    """Build the list of [[provider]] TOML entries.

    If no providers are given, returns a default single-entry list with
    the hardcoded "openstack" provider for backward compatibility.

    Args:
        providers: List of provider config dicts from Configurator units,
            each with keys: unit_name, auth_url, username, password,
            project_name, user_domain_name, project_domain_name,
            region_name, network, image_id.

    Returns:
        A list of provider dicts suitable for TOML rendering.
    """
    if not providers:
        return [
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
        ]

    result: list[dict[str, typing.Any]] = []
    for p in providers:
        result.append(
            {
                "name": p["unit_name"],
                "provider_type": "external",
                "description": f"OpenStack provider ({p['unit_name']})",
                "external": {
                    "config_file": "",
                    "provider_executable": OPENSTACK_PROVIDER_BINARY,
                    "environment_variables": [
                        f"OPENSTACK_AUTH_URL={p['auth_url']}",
                        f"OPENSTACK_USERNAME={p['username']}",
                        f"OPENSTACK_PASSWORD={p['password']}",
                        f"OPENSTACK_PROJECT_NAME={p['project_name']}",
                        f"OPENSTACK_USER_DOMAIN_NAME={p['user_domain_name']}",
                        f"OPENSTACK_PROJECT_DOMAIN_NAME={p['project_domain_name']}",
                        f"OPENSTACK_REGION_NAME={p['region_name']}",
                        f"OPENSTACK_NETWORK={p['network']}",
                        f"OPENSTACK_IMAGE_ID={p['image_id']}",
                    ],
                },
            }
        )
    return result


def render_garm_toml(
    *,
    listen_address: str,
    listen_port: int,
    jwt_secret: str,
    db_passphrase: str,
    postgresql_config: dict[str, typing.Any],
    providers: list[dict[str, str]] | None = None,
) -> str:
    """Render GARM's TOML configuration file content.

    Args:
        listen_address: IP address for the GARM API server to bind on.
        listen_port: Port for the GARM API server.
        jwt_secret: Secret string used to sign GARM JWT tokens.
        db_passphrase: 32-character passphrase for AES-256 encryption of secrets in the DB.
        postgresql_config: PostgreSQL connection parameters (username, password,
            hostname, port, database, sslmode).
        providers: Optional list of provider config dicts from Configurator
            units. If None or empty, a default single "openstack" provider
            is used for backward compatibility.

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
        "provider": _build_provider_list(providers),
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
        postgresql_config = self._get_postgresql_config()
        if not postgresql_config:
            logger.info("PostgreSQL relation data not yet available; blocking")
            self.unit.status = ops.BlockedStatus("Waiting for postgresql relation")
            return

        # Render TOML including dynamic providers from Configurator relation
        secrets_for_toml = self._get_secrets()
        provider_configs = self._get_configurator_provider_configs()
        toml_content = render_garm_toml(
            listen_address=str(self.config.get("garm-listen-address", "0.0.0.0")),
            listen_port=int(self.config.get("garm-listen-port", 9997)),
            jwt_secret=secrets_for_toml["jwt-secret"],
            db_passphrase=secrets_for_toml["db-passphrase"],
            postgresql_config=postgresql_config,
            providers=provider_configs if provider_configs else None,
        )

        # Hash the rendered TOML — skip restart if unchanged
        new_hash = self._hash_toml(toml_content)
        previous_hash = self._get_stored_toml_hash()
        if previous_hash == new_hash:
            logger.debug("TOML config unchanged; skipping restart")
            return

        container = self.unit.get_container(CONTAINER_NAME)
        container.push(GARM_CONFIG_PATH, toml_content, make_dirs=True)
        self._store_toml_hash(new_hash)

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

    @staticmethod
    def _hash_toml(toml_content: str) -> str:
        """Return the SHA-256 hex digest of the given TOML content.

        Args:
            toml_content: The TOML string to hash.

        Returns:
            A 64-character hex digest string.
        """
        return hashlib.sha256(toml_content.encode("utf-8")).hexdigest()

    def _get_stored_toml_hash(self) -> str | None:
        """Retrieve the stored TOML hash from the Juju secret, or None.

        Returns:
            The stored SHA-256 hash string, or None if no hash has been
            stored yet.
        """
        try:
            secret = self.model.get_secret(label=TOML_HASH_LABEL)
            return secret.get_content().get("sha256")
        except ops.SecretNotFoundError:
            return None

    def _store_toml_hash(self, hash_value: str) -> None:
        """Store the TOML hash in a Juju secret.

        Creates or updates the secret labelled TOML_HASH_LABEL.

        Args:
            hash_value: The SHA-256 hex digest to store.
        """
        try:
            secret = self.model.get_secret(label=TOML_HASH_LABEL)
            secret.set_content({"sha256": hash_value})
        except ops.SecretNotFoundError:
            self.app.add_secret({"sha256": hash_value}, label=TOML_HASH_LABEL)

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

    def _get_configurator_provider_configs(
        self,
    ) -> list[dict[str, str]]:
        """Read OpenStack provider configs from all Configurator units.

        Each Configurator unit writes its provider config to unit-level
        relation data on the ``garm-configurator`` endpoint. This method
        collects all such configs, keyed by unit name for TOML provider
        naming.

        Returns:
            A list of dicts, each containing the provider config fields
            (auth_url, username, password, project_name, user_domain_name,
            project_domain_name, region_name, network, image_id) plus a
            ``unit_name`` key for the provider's TOML name. Returns an
            empty list if no Configurator units are connected.
        """
        relation = self.model.get_relation(GARM_CONFIGURATOR_RELATION_NAME)
        if relation is None:
            return []

        configs: list[dict[str, str]] = []
        for unit in relation.units:
            data = relation.data[unit]
            # Only include units that have sent the full provider config
            if "openstack_auth_url" not in data:
                continue
            configs.append(
                {
                    "unit_name": unit.name.replace("/", "-"),
                    "auth_url": data.get("openstack_auth_url", ""),
                    "username": data.get("openstack_username", ""),
                    "password": data.get("openstack_password", ""),
                    "project_name": data.get("openstack_project_name", ""),
                    "user_domain_name": data.get("openstack_user_domain_name", ""),
                    "project_domain_name": data.get("openstack_project_domain_name", ""),
                    "region_name": data.get("openstack_region_name", ""),
                    "network": data.get("openstack_network", ""),
                    "image_id": data.get("image_id", ""),
                }
            )
        return configs


if __name__ == "__main__":
    ops.main(GarmCharm)
