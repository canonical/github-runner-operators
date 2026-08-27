#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import dataclasses
import json
import logging
import os
import secrets
import string
import typing
from collections.abc import Mapping

import ops
import paas_charm.go
from paas_charm.app import WorkloadConfig
from paas_charm.charm_state import CharmState as PaasCharmState
from paas_charm.charm_utils import block_if_invalid_data

from charm_state import (
    DEBUG_SSH_INTEGRATION_NAME,
    GARM_CONFIGURATOR_RELATION_NAME,
    CharmState,
    RunnerConfig,
    credential_name,
    resolve_entity,
)
from entity_reconciler import EntityReconciler
from garm_api import GarmApiClient, GarmApiError, GarmAuthenticatedClient, GarmConnectionError
from garm_template import CharmedTemplateError
from garm_template import apply_charmed_template as _apply_garm_template
from github_reconciler import (
    DEFAULT_GITHUB_ENDPOINT,
    MANAGED_CREDENTIAL_DESCRIPTION,
    CredentialSpec,
    GithubReconciler,
)
from resource_cleanup import GarmCleanupError, GarmResourceCleanup
from scaleset_reconciler import ScalesetReconciler, ScalesetSpec

logger = logging.getLogger(__name__)

GARM_PROVIDER_CONFIG_DIR: typing.Final[str] = "/etc/garm"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
GARM_ADMIN_CREDENTIALS_LABEL: typing.Final[str] = "garm-admin-credentials"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_PORT: typing.Final[int] = 8080
GARM_LOCAL_API_BASE_URL: typing.Final[str] = f"http://127.0.0.1:{GARM_PORT}/api/v1"
GARM_LISTEN_ADDRESS: typing.Final[str] = "0.0.0.0"
_DB_PASSPHRASE_LENGTH: typing.Final[int] = 32

GARM_CONFIG_VERSION: typing.Final[str] = "1"


def _generate_passphrase(length: int = _DB_PASSPHRASE_LENGTH) -> str:
    """Generate a random alphanumeric passphrase for GARM DB encryption.

    Args:
        length: Length of the passphrase (default 32 for AES-256).

    Returns:
        Random alphanumeric string of the given length.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


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
    symbols = "!@#$%-_=+"
    alphabet = string.ascii_letters + string.digits + symbols
    mandatory = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(symbols),
    ]
    filler = [secrets.choice(alphabet) for _ in range(16)]
    chars = mandatory + filler
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def _parse_pre_install_scripts(raw: str) -> dict[str, str]:
    """Parse pre_install_scripts from JSON relation data string."""
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except ValueError:
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
        self.framework.observe(self.on.install, self._reconcile)
        self.framework.observe(self.on.leader_elected, self._reconcile)
        self.framework.observe(
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_joined,
            self._reconcile,
        )
        self.framework.observe(
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_changed,
            self._reconcile,
        )
        self.framework.observe(
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_departed,
            self._reconcile,
        )
        self.framework.observe(
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_broken,
            self._reconcile,
        )
        self.framework.observe(self.on.get_credentials_action, self._on_get_credentials_action)
        self.framework.observe(
            self.on[DEBUG_SSH_INTEGRATION_NAME].relation_joined,
            self._reconcile,
        )
        self.framework.observe(
            self.on[DEBUG_SSH_INTEGRATION_NAME].relation_changed,
            self._reconcile,
        )
        self.framework.observe(
            self.on[DEBUG_SSH_INTEGRATION_NAME].relation_departed,
            self._reconcile,
        )
        self.framework.observe(
            self.on[DEBUG_SSH_INTEGRATION_NAME].relation_broken,
            self._reconcile,
        )
        self.framework.observe(self.on.update_status, self._reconcile)
        self.framework.observe(self.on.remove, self._on_remove)

    def _is_tearing_down(self) -> bool:
        """Return whether Juju plans no remaining units for the local application."""
        return self.app.planned_units() == 0

    def _reconcile(self, event: ops.EventBase) -> None:
        """Skip normal reconciliation once local application teardown starts."""
        if self._is_tearing_down():
            logger.info(
                "Skipping normal GARM reconciliation for %s during local teardown",
                event.handle.kind,
            )
            return
        self._normal_reconcile(event)

    @block_if_invalid_data
    def _normal_reconcile(self, _: ops.EventBase) -> None:
        """Reconcile active GARM charm state."""
        self.restart()

    def _create_charm_state(self) -> PaasCharmState:
        """Create framework state without reading relations during local teardown."""
        if self._is_tearing_down():
            return PaasCharmState(
                framework=self._framework_name,
                is_secret_storage_ready=False,
            )
        return super()._create_charm_state()

    def _on_update_status(self, event: ops.HookEvent) -> None:
        """Run the framework update-status handler only while active."""
        if self._is_tearing_down():
            logger.info("Skipping update-status handling during local teardown")
            return
        super()._on_update_status(event)

    def _on_remove(self, _: ops.RemoveEvent) -> None:
        """Drain GARM resources before Juju removes the application."""
        if not self.unit.is_leader():
            logger.info("Skipping GARM removal cleanup on a non-leader unit")
            return
        if self.app.planned_units() > 0:
            logger.info(
                "Skipping GARM removal cleanup while the application still has planned units"
            )
            return

        initialization_client = GarmApiClient(GARM_LOCAL_API_BASE_URL)
        try:
            if not initialization_client.is_initialized():
                logger.info(
                    "GARM has not completed first-run; no resources require removal cleanup"
                )
                return
        except GarmConnectionError as exc:
            if self._get_postgresql_config() is None:
                logger.info(
                    "PostgreSQL is not configured and GARM is unreachable; "
                    "GARM cannot have been initialized, so no cleanup is required"
                )
                return
            message = (
                f"Cannot determine whether GARM was initialized: {exc}. "
                "Operator action: restore GARM/API availability, then retry "
                "Juju application removal."
            )
            logger.error(message)
            raise GarmCleanupError(message) from exc
        except GarmApiError as exc:
            message = (
                f"Cannot determine whether GARM was initialized: {exc}. "
                "Operator action: restore GARM/API availability, then retry "
                "Juju application removal."
            )
            logger.error(message)
            raise GarmCleanupError(message) from exc

        admin_creds = self._get_admin_credentials()
        if not admin_creds:
            message = (
                "GARM admin credentials are unavailable; refusing removal. "
                "Operator action: restore the labelled admin credentials secret, "
                "then retry Juju application removal."
            )
            logger.error(message)
            raise GarmCleanupError(message)

        username = admin_creds.get("username")
        password = admin_creds.get("password")
        if not username or not password:
            message = (
                "GARM admin credentials are incomplete; refusing removal. "
                "Operator action: restore username and password in the labelled "
                "admin credentials secret, then retry Juju application removal."
            )
            logger.error(message)
            raise GarmCleanupError(message)

        base_url = GARM_LOCAL_API_BASE_URL
        try:
            auth_client = GarmAuthenticatedClient.from_login(base_url, username, password)
            GarmResourceCleanup(auth_client).run()
        except GarmApiError as exc:
            logger.error(
                "GARM removal cleanup failed: %s. Operator action: resolve the "
                "reported GARM/API/runner issue, then retry Juju application removal.",
                exc,
            )
            raise

    def _on_get_credentials_action(self, event: ops.ActionEvent) -> None:
        """Return the GARM admin credentials to the operator.

        Args:
            event: The action event.
        """
        credentials = self._get_admin_credentials()
        if credentials is None:
            event.fail("GARM admin credentials are not yet available")
            return
        event.set_results(credentials)

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
        return dataclasses.replace(
            super()._workload_config,
            port=GARM_PORT,
            metrics_target=None,
            service_name=PEBBLE_SERVICE_NAME,
        )

    def restart(self, rerun_migrations: bool = False) -> None:
        """Configure the wrapper and restart the workload.

        Ensures secrets before the readiness gate so they exist on
        install/leader_elected before pebble is ready, then gates on
        workload readiness before writing config and replanning.

        Args:
            rerun_migrations: Passed through to the parent restart.
        """
        if self._is_tearing_down():
            logger.info("Skipping GARM workload restart during local teardown")
            return

        self._ensure_secrets()

        if not self.is_ready():
            logger.info("GARM workload prerequisites are not ready; waiting")
            return

        self._warn_unsupported_port_options()

        postgresql_config = self._get_postgresql_config()
        if not postgresql_config:
            logger.info("PostgreSQL relation data not yet available; blocking")
            self.update_app_and_unit_status(ops.WaitingStatus("Waiting for postgresql relation"))
            return

        secrets_data = self._get_secrets()
        if secrets_data is None:
            logger.info("GARM secrets not yet available; blocking until leader initialises")
            self.update_app_and_unit_status(ops.WaitingStatus("Waiting for GARM secrets"))
            return

        provider_configs = self._get_configurator_provider_configs()
        if not provider_configs:
            if not CharmState.from_charm(self).configurator_related:
                self._reconcile_runners()
            logger.info("GARM configurator provider data not yet available; blocking")
            self.update_app_and_unit_status(
                ops.WaitingStatus("Waiting for garm-configurator relation")
            )
            return

        container = self.unit.get_container(CONTAINER_NAME)
        entrypoint_environment = self._entrypoint_environment(
            postgresql_config, secrets_data, provider_configs
        )
        super().restart(rerun_migrations=rerun_migrations)
        container.add_layer(
            "garm-command",
            {
                "services": {
                    PEBBLE_SERVICE_NAME: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "/usr/local/bin/garm-entrypoint.py",
                        "environment": entrypoint_environment,
                    }
                }
            },
            combine=True,
        )
        logger.info(
            "Configured GARM workload: command=%s provider_count=%d env_keys=%s",
            "/usr/local/bin/garm-entrypoint.py",
            len(provider_configs),
            sorted(entrypoint_environment),
        )
        container.replan()
        self._maybe_first_run()
        # Reconcile last: the framework's restart finishes by reporting active unconditionally,
        # which would bury the status a failed GARM sync reports here.
        self._reconcile_runners()

    def _entrypoint_environment(
        self,
        postgresql_config: dict[str, typing.Any],
        secrets_data: dict[str, str],
        provider_configs: list[dict[str, str]],
    ) -> dict[str, str]:
        """Build the environment consumed by the GARM entrypoint."""
        environment = {
            "POSTGRESQL_DB_HOSTNAME": str(postgresql_config["hostname"]),
            "POSTGRESQL_DB_PORT": str(postgresql_config["port"]),
            "POSTGRESQL_DB_USERNAME": str(postgresql_config["username"]),
            "POSTGRESQL_DB_PASSWORD": str(postgresql_config["password"]),
            "POSTGRESQL_DB_NAME": str(postgresql_config["database"]),
            "GARM_JWT_SECRET": secrets_data["jwt-secret"],
            "GARM_PASSPHRASE": secrets_data["db-passphrase"],
            "GARM_PROVIDERS_JSON": json.dumps(
                provider_configs, sort_keys=True, separators=(",", ":")
            ),
            "APP_BASE_URL": self._base_url,
        }
        for juju_name, name in {
            "JUJU_CHARM_HTTP_PROXY": "http_proxy",
            "JUJU_CHARM_HTTPS_PROXY": "https_proxy",
            "JUJU_CHARM_NO_PROXY": "no_proxy",
        }.items():
            value = os.environ.get(juju_name, "").strip()
            if value:
                environment[name] = value
                environment[name.upper()] = value
        return environment

    def _warn_unsupported_port_options(self) -> None:
        """Warn when app-port/metrics-port/metrics-path are set to non-default values.

        GARM serves its API and metrics on the same fixed port (GARM_PORT) — it has no separate
        metrics listener — and declares its scrape target in paas-config.yaml, so the
        go-framework's app-port/metrics-port/metrics-path settings don't apply. _workload_config
        also pins the workload port to GARM_PORT, so app-port has no effect on ingress, the opened
        ports, or the service URL (they can't drift from GARM's actual port). Warn rather than
        block when an operator sets any to a non-default value, tolerating their absence (the
        framework may drop them in future).
        """
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

    def _ensure_secrets(self) -> None:
        """Create garm-secrets and garm-admin-credentials (leader only)."""
        if not self.unit.is_leader():
            return
        try:
            self.model.get_secret(label=GARM_SECRETS_LABEL)
        except ops.SecretNotFoundError:
            logger.info("GARM secrets not yet available; creating them")
            self.app.add_secret(_generate_garm_secrets(), label=GARM_SECRETS_LABEL)
        try:
            self.model.get_secret(label=GARM_ADMIN_CREDENTIALS_LABEL)
        except ops.SecretNotFoundError:
            logger.info("GARM admin credentials not yet available; creating them")
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

    def _get_secrets(self) -> dict[str, str] | None:
        """Retrieve secrets from the juju secret store.

        Returns:
            Dict with jwt-secret and db-passphrase, or None if the
            secret is not accessible (e.g. not yet created by the leader).
        """
        try:
            secret = self.model.get_secret(label=GARM_SECRETS_LABEL)
            return secret.get_content()
        except ops.SecretNotFoundError:
            return None

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

        Passwords stored as Juju secret URIs are resolved at this point
        so that the plaintext value is available for the provider's
        clouds.yaml file.

        Returns:
            A list of dicts, each containing the provider config fields
            (auth_url, username, password, project_name, etc.) plus a
            ``unit_name`` key for the provider's TOML name.
        """
        relation = self.model.get_relation(GARM_CONFIGURATOR_RELATION_NAME)
        if relation is None:
            logger.info("GARM configurator relation not available; provider_count=0")
            return []

        configs: list[dict[str, str]] = []
        for unit in sorted(relation.units, key=lambda unit: unit.name):
            data = relation.data[unit]
            # Only include units that have sent the full provider config
            if "openstack_auth_url" not in data:
                continue

            # Resolve password: may be a plain value or a secret URI.
            password = data.get("openstack_password", "")
            unit_name = unit.name.replace("/", "-")
            password_secret_uri = data.get("openstack_password_secret_uri", "")
            if not password and password_secret_uri:
                password = self._resolve_secret_value(str(password_secret_uri))

            configs.append(
                {
                    "unit_name": unit_name,
                    "auth_url": data.get("openstack_auth_url", ""),
                    "username": data.get("openstack_username", ""),
                    "password": password,
                    "project_name": data.get("openstack_project_name", ""),
                    "user_domain_name": data.get("openstack_user_domain_name", ""),
                    "project_domain_name": data.get("openstack_project_domain_name", ""),
                    "region_name": data.get("openstack_region_name", ""),
                    "network": data.get("openstack_network", ""),
                }
            )

        logger.info(
            "GARM configurator provider data: relation_unit_count=%d configured_provider_count=%d",
            len(relation.units),
            len(configs),
        )
        return configs

    def _resolve_secret_value(self, secret_uri: str) -> str:
        """Resolve a secret URI and return its ``value`` content.

        Args:
            secret_uri: A Juju secret URI.

        Returns:
            The ``value`` field from the secret's content, or an empty
            string if the secret is not accessible.
        """
        try:
            secret = self.model.get_secret(id=secret_uri)
            return secret.get_content(refresh=True).get("value", "")
        except (ops.SecretNotFoundError, ops.ModelError):
            # Secret grants can race the relation-joined hook. The following
            # relation-changed event retries once Juju has propagated access.
            logger.warning("Secret %s is not accessible yet", secret_uri)
            return ""

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

        client = GarmApiClient(GARM_LOCAL_API_BASE_URL)

        try:
            client.wait_for_ready()
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
            logger.warning("GARM first-run check failed (error out for retry): %s", exc)
            raise

    def _build_desired_scalesets(self, template_id: int | None) -> list[ScalesetSpec]:
        """Build the desired scaleset list from all garm-configurator relation units."""
        specs = []
        for relation in self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []):
            for unit in relation.units:
                spec = self._build_scaleset_spec(relation.data[unit], template_id)
                if spec is not None:
                    specs.append(spec)
        return specs

    @staticmethod
    def _build_scaleset_spec(
        data: Mapping[str, str], template_id: int | None
    ) -> ScalesetSpec | None:
        """Build the scaleset spec described by one configurator unit's databag.

        Args:
            data: The relation unit databag.
            template_id: The charmed runner template the scaleset references.

        Returns:
            The spec, or None when the databag names no scaleset or is incomplete
            or invalid, so the caller can skip the unit. Skips are logged except
            for malformed ``min_idle_runner``/``max_runner`` values, which skip
            silently.
        """
        name = data.get("name", "")
        if not name:
            return None

        entity = resolve_entity(data)
        if entity is None:
            logger.warning("Skipping scaleset %s: neither org nor repo specified", name)
            return None
        entity_type, entity_name = entity

        required = {
            "provider_name": data.get("provider_name", ""),
            "image": data.get("image_id", ""),
            "flavor": data.get("flavor", ""),
            "os_arch": data.get("os_arch", ""),
            "max_runner": data.get("max_runner", ""),
        }
        missing = [field for field, value in required.items() if not value]
        if missing:
            logger.warning("Skipping scaleset %s: missing required fields %s", name, missing)
            return None
        try:
            min_idle = int(data.get("min_idle_runner", "0"))
            max_runners = int(required["max_runner"])
        except ValueError:
            return None
        return ScalesetSpec(
            name=name,
            provider_name=required["provider_name"],
            image=required["image"],
            flavor=required["flavor"],
            os_arch=required["os_arch"],
            os_type="linux",
            min_idle_runners=min_idle,
            max_runners=max_runners,
            entity_type=entity_type,
            entity_name=entity_name,
            labels=[label.strip() for label in data.get("labels", "").split(",") if label.strip()],
            runner_group=data.get("runner_group", ""),
            pre_install_scripts=_parse_pre_install_scripts(data.get("pre_install_scripts", "")),
            template_id=template_id,
            runner_config=RunnerConfig.from_databag(data),
        )

    def _build_desired_credentials(self) -> list[CredentialSpec]:
        """Build desired GitHub credentials from configurator relation data.

        Credentials are deduped per (app_id, installation_id) so multiple configurator
        units sharing one GitHub App yield a single GARM credential. The App private key
        is sourced only from the Juju secret referenced by ``github_private_key_secret_uri``
        — never from plaintext relation data. Credentials attach to GARM's built-in
        ``github.com`` endpoint.

        Returns:
            The full desired set of GitHub credential specs.
        """
        credentials: dict[tuple[int, int], CredentialSpec] = {}
        for relation in self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []):
            for unit in relation.units:
                self._add_unit_credential(credentials, relation.data[unit], unit.name)
        return list(credentials.values())

    def _add_unit_credential(
        self,
        credentials: dict[tuple[int, int], CredentialSpec],
        data: Mapping[str, str],
        unit_name: str,
    ) -> None:
        """Add the GitHub credential described by one configurator unit.

        The unit is skipped — quietly — when its (app_id, installation_id) pair
        was already provided by an earlier unit (the dedupe) or its App fields
        are merely absent, and with a warning when the ids are malformed or the
        private-key secret is unreadable.

        Args:
            credentials: The accumulating desired credentials, keyed by
                (app_id, installation_id).
            data: The relation unit databag.
            unit_name: The configurator unit's name, for log messages.
        """
        app_id_raw = data.get("github_app_id", "")
        installation_id_raw = data.get("github_installation_id", "")
        key_secret_uri = data.get("github_private_key_secret_uri", "")
        if not (app_id_raw and installation_id_raw and key_secret_uri):
            return
        try:
            app_id = int(app_id_raw)
            installation_id = int(installation_id_raw)
        except ValueError:
            logger.warning(
                "Skipping GitHub credential from %s: non-numeric app/installation id "
                "(app_id=%r, installation_id=%r)",
                unit_name,
                app_id_raw,
                installation_id_raw,
            )
            return

        dedupe_key = (app_id, installation_id)
        if dedupe_key in credentials:
            return

        private_key = self._resolve_secret_value(str(key_secret_uri))
        if not private_key:
            logger.warning(
                "Skipping GitHub credential for app %s: private key secret unavailable",
                app_id,
            )
            return

        credentials[dedupe_key] = CredentialSpec(
            name=credential_name(app_id, installation_id),
            endpoint=DEFAULT_GITHUB_ENDPOINT,
            app_id=app_id,
            installation_id=installation_id,
            private_key=private_key,
            description=MANAGED_CREDENTIAL_DESCRIPTION,
        )

    def _reconcile_runners(self) -> None:
        """Sync GARM controller URLs, GitHub credentials, entities, then scalesets.

        The steps are ordered, not independent: GARM rejects every operational call with
        409 ``urls_required`` until the controller URLs are set; org/repo entities reference a
        credential by name; and scalesets are created under a registered entity. So a single
        authenticated client configures the URLs and reconciles credentials, then entities,
        then scalesets. The ``github_linux_charmed`` template is ensured before scalesets so each
        scaleset can reference it.
        """
        admin_creds = self._get_admin_credentials()
        if not admin_creds:
            logger.warning("Admin credentials not yet available; deferring reconcile")
            return

        # Talk to GARM over its fixed local listener (same target as first-run), rather than
        # _get_garm_url() which depends on charm config that is not set for the local API.
        base_url = GARM_LOCAL_API_BASE_URL
        try:
            charm_state = CharmState.from_charm(self)
            auth_client = GarmAuthenticatedClient.from_login(
                base_url, admin_creds["username"], admin_creds["password"]
            )
            # The steps are ordered, not independent: GARM rejects every operational call with 409
            # ``urls_required`` until the controller URLs are set; org/repo entities reference a
            # credential by name; and scalesets are created under a registered entity. So a single
            # authenticated client configures the URLs and reconciles credentials, then entities,
            # then scalesets — each dependency before its dependants.
            self._ensure_controller_urls(auth_client)
            GithubReconciler(auth_client).reconcile(self._build_desired_credentials())
            EntityReconciler(auth_client).reconcile(charm_state.desired_entities)
            template_id = _apply_garm_template(auth_client, charm_state.ssh_debug_connections)
            ScalesetReconciler(auth_client).reconcile(self._build_desired_scalesets(template_id))
            self.update_app_and_unit_status(ops.ActiveStatus())
        except CharmedTemplateError as exc:
            logger.warning("GARM charmed template error during reconcile: %s", exc)
            self.update_app_and_unit_status(ops.WaitingStatus(str(exc)))
        except GarmApiError as exc:
            logger.warning("GARM API error during reconcile: %s", exc)
            self.update_app_and_unit_status(ops.WaitingStatus("GARM sync failed"))

    def _ensure_controller_urls(self, auth_client: GarmAuthenticatedClient) -> None:
        """Configure the GARM controller URLs that gate its operational API.

        GARM returns 409 ``urls_required`` on credential/endpoint/scaleset operations until
        the metadata and callback URLs are set. The base is the application's reachable URL
        provided by the go framework: the external ingress URL when an ingress relation is
        present, otherwise the in-cluster Kubernetes service URL. Runners reach the
        metadata/callback paths through it, and GitHub reaches the webhook path; both require
        the public ingress URL, so this is re-run when ingress becomes ready or is revoked.
        """
        base = self._base_url.rstrip("/")
        auth_client.update_controller(
            metadata_url=f"{base}/api/v1/metadata",
            callback_url=f"{base}/api/v1/callbacks",
            webhook_url=f"{base}/webhooks",
        )


if __name__ == "__main__":
    ops.main(GarmCharm)
