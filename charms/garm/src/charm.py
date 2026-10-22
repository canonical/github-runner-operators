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
from paas_charm.charm_utils import block_if_invalid_data

from agent_tools import AgentToolsError, ensure_agent_tools
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
from garm_client.models.scale_set import ScaleSet
from garm_entrypoint import PROVIDER_REQUIRED_FIELDS
from garm_template import CharmedTemplateError
from garm_template import apply_charmed_template as _apply_garm_template
from github_reconciler import (
    DEFAULT_GITHUB_ENDPOINT,
    MANAGED_CREDENTIAL_DESCRIPTION,
    CredentialSpec,
    GithubReconciler,
)
from resource_cleanup import GarmCleanupError, GarmResourceCleanup
from scaleset_reconciler import Handover, ScalesetProgress, ScalesetReconciler, ScalesetSpec
from security_log import owasp_log

logger = logging.getLogger(__name__)

GARM_PROVIDER_CONFIG_DIR: typing.Final[str] = "/etc/garm"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
GARM_ADMIN_CREDENTIALS_LABEL: typing.Final[str] = "garm-admin-credentials"
# The provider set GARM was last started with. Kept in a secret, not only in the Pebble
# plan, so it survives a pod replacement and is shared by every unit: a drain can run for
# days, and a restart with a shrunken set in the middle of one strands the scaleset.
GARM_PROVIDERS_LABEL: typing.Final[str] = "garm-providers"
GARM_PROVIDERS_SECRET_KEY: typing.Final[str] = "providers"


class ProviderRecordError(Exception):
    """The provider record could not be read or written, so the provider set is unknown."""


CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_PORT: typing.Final[int] = 8080
GARM_LOCAL_API_BASE_URL: typing.Final[str] = f"http://127.0.0.1:{GARM_PORT}/api/v1"
GARM_LISTEN_ADDRESS: typing.Final[str] = "0.0.0.0"
_DB_PASSPHRASE_LENGTH: typing.Final[int] = 32
# Juju truncates long statuses; name a couple of scalesets and count the rest.
_MAX_DRAINING_IN_STATUS: typing.Final[int] = 2
# The phases a scaleset replacement passes through, in order. Named here rather than
# spelled inline so the status vocabulary is greppable; not an enum, because the
# draining phase carries the runner count and so is formatted, not selected.
_PHASE_CREATING: typing.Final[str] = "creating replacement"
_PHASE_RETIRING: typing.Final[str] = "retiring predecessor"
_PHASE_AWAITING_DELETION: typing.Final[str] = "awaiting deletion"

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


def _parse_provider_record(published: str, source: str) -> list[dict[str, str]]:
    """Parse a recorded provider set, rejecting anything that cannot drive GARM.

    Args:
        published: The recorded JSON value.
        source: Where the value came from, for the error message.

    Returns:
        The provider configs.

    Raises:
        ProviderRecordError: If the value is not a list of complete provider configs. A
            partially read record would publish providers missing credentials, which stops
            the workload from starting — the same failure, later and less legible.
    """
    if not published:
        return []
    try:
        configs = json.loads(published)
    except json.JSONDecodeError as exc:
        raise ProviderRecordError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(configs, list):
        raise ProviderRecordError(f"{source} is not a list of providers")
    for config in configs:
        if not isinstance(config, dict) or not isinstance(config.get("unit_name"), str):
            raise ProviderRecordError(f"{source} holds a provider with no unit name")
        missing = [field for field in PROVIDER_REQUIRED_FIELDS if not config.get(field)]
        if missing:
            raise ProviderRecordError(
                f"{source} holds provider {config['unit_name']} without {', '.join(missing)}"
            )
    return configs


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

    @block_if_invalid_data
    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state."""
        self.restart()

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
            owasp_log.sys_shutdown(
                userid=username,
                description="GARM application teardown: draining resources before removal",
            )
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
        owasp_log.authz_admin(
            userid=self.unit.name,
            admin_activity="get_credentials",
            description="GARM admin credentials disclosed via Juju action",
        )
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

        The provider set is read, published, reconciled and then trimmed and recorded, once
        each, in that order. A provider joins the record when a relation publishes it and
        leaves it only when no relation publishes it and no scaleset GARM still holds names
        it. Keep that order: GARM fixes its provider map per process, so a scaleset whose
        provider was dropped first can never be drained or deleted.

        Args:
            rerun_migrations: Passed through to the parent restart.
        """
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

        related_providers = self._get_configurator_provider_configs()
        recorded_providers = self._read_provider_record()
        configurator_related = CharmState.from_charm(self).configurator_related
        # The record is published even with no relation left: a drain outlives the relation,
        # and a replaced pod must start GARM with the providers that drain needs. An empty
        # set is published the same way, so the workload converges on what the relations and
        # the record justify instead of keeping a set that nothing stands behind.
        published_providers = self._published_providers(related_providers, recorded_providers)

        container = self.unit.get_container(CONTAINER_NAME)
        entrypoint_environment = self._entrypoint_environment(
            postgresql_config, secrets_data, published_providers
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
            len(published_providers),
            sorted(entrypoint_environment),
        )
        container.replan()
        self._maybe_first_run()
        # Reconcile before recording: the pass is what establishes which providers are still
        # referenced, and it must not be buried by the framework reporting active afterward.
        #
        # The chain iterates the desired state, so an empty one reconciles to zero. It must
        # not, however, read silence as "nothing is desired": every reconciler deletes what
        # it is not told to keep, so a configurator that has not published yet would lose the
        # credentials, entities and scalesets it is about to describe. Only a relation that
        # has published, or no configurator at all, is a complete desired state.
        if related_providers or not configurator_related:
            referenced_providers = self._reconcile_runners()
            self._save_provider_record(
                self._trimmed_providers(
                    published_providers, related_providers, referenced_providers
                )
            )
        else:
            logger.info("GARM configurator provider data not yet available; blocking")
        if not related_providers:
            self.update_app_and_unit_status(
                ops.WaitingStatus("Waiting for garm-configurator relation")
            )

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
        """Read OpenStack provider configs from all Configurator applications.

        Each Configurator application is expected to have one unit, which
        writes its provider config to unit-level relation data on the
        ``garm-configurator`` endpoint. If an application has multiple units,
        its first unit by name is used. This method collects one config from
        each application, keyed by unit name for TOML provider naming.

        Passwords stored as Juju secret URIs are resolved at this point
        so that the plaintext value is available for the provider's
        clouds.yaml file.

        Returns:
            A list of dicts, each containing the provider config fields
            (auth_url, username, password, project_name, etc.) plus a
            ``unit_name`` key for the provider's TOML name.
        """
        relations = sorted(
            self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []),
            key=lambda relation: relation.id,
        )
        if not relations:
            logger.info("GARM configurator relation not available; provider_count=0")
            return []

        configs: list[dict[str, str]] = []
        for relation in relations:
            units = sorted(relation.units, key=lambda unit: unit.name)
            if not units:
                logger.warning(
                    "GARM configurator application has no units: relation_id=%d",
                    relation.id,
                )
                continue
            if len(units) > 1:
                logger.warning(
                    "GARM configurator application has multiple units; using first unit: "
                    "relation_id=%d unit_count=%d unit=%s",
                    relation.id,
                    len(units),
                    units[0].name,
                )

            unit = units[0]
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
            sum(len(relation.units) for relation in relations),
            len(configs),
        )
        return configs

    def _published_providers(
        self, related: list[dict[str, str]], recorded: dict[str, dict[str, str]]
    ) -> list[dict[str, str]]:
        """Return the provider set to publish: the record with the relations on top.

        Args:
            related: The provider configs the remaining relations publish.
            recorded: The recorded configs, by provider name.

        Returns:
            The provider set to publish, ordered by provider name. Relation data wins, so a
            rotated password reaches GARM.
        """
        merged = {
            **recorded,
            **{config["unit_name"]: config for config in related},
        }
        return sorted(merged.values(), key=lambda config: config["unit_name"])

    def _read_provider_record(self) -> dict[str, dict[str, str]]:
        """Return the recorded provider set, by provider name.

        Returns:
            The recorded configs, or an empty mapping when nothing has been recorded yet.

        Raises:
            ProviderRecordError: If the record exists but cannot be read, or does not hold a
                usable provider set: publishing from it would drop providers a live scaleset
                still needs.
        """
        try:
            secret = self.model.get_secret(label=GARM_PROVIDERS_LABEL)
            # Latest revision without tracking it: the record is written by this application
            # only, and a read one revision behind would resurrect a provider the previous
            # hook trimmed away.
            content = secret.peek_content()
        except ops.SecretNotFoundError:
            logger.info("No recorded GARM provider set; publishing the relations only")
            return {}
        except ops.ModelError as exc:
            raise ProviderRecordError(f"cannot read the GARM provider record: {exc}") from exc
        recorded = _parse_provider_record(
            content.get(GARM_PROVIDERS_SECRET_KEY, ""), "the GARM provider record"
        )
        return {config["unit_name"]: config for config in recorded}

    @staticmethod
    def _trimmed_providers(
        published: list[dict[str, str]],
        related: list[dict[str, str]],
        scalesets: list[ScaleSet] | None,
    ) -> list[dict[str, str]]:
        """Drop providers no relation publishes and no live scaleset names.

        Args:
            published: The provider set GARM was started with on this pass.
            related: The provider configs the remaining relations publish.
            scalesets: The scalesets GARM still holds after the pass, or None when the pass
                could not establish that.

        Returns:
            The set to record; ``published`` unchanged when the surviving scalesets are
            unknown, or when one of them names no provider — "no scaleset references it"
            cannot be concluded from "could not tell".
        """
        if scalesets is None:
            logger.warning(
                "The scalesets GARM still holds could not be read; keeping every provider"
                " this hook: %s",
                sorted(config["unit_name"] for config in published),
            )
            return published
        unmapped = [scaleset.name for scaleset in scalesets if not scaleset.provider_name]
        if unmapped:
            logger.warning(
                "Scalesets %s name no provider, so the provider set cannot be mapped to the"
                " scalesets GARM holds; keeping every provider this hook: %s",
                unmapped,
                sorted(config["unit_name"] for config in published),
            )
            return published

        related_names = {config["unit_name"] for config in related}
        referenced = {scaleset.provider_name for scaleset in scalesets if scaleset.provider_name}
        kept = [
            config
            for config in published
            if config["unit_name"] in related_names or config["unit_name"] in referenced
        ]
        kept_names = {config["unit_name"] for config in kept}
        for name in sorted({config["unit_name"] for config in published} - kept_names):
            logger.info("Removing provider %s: no scaleset references it any more", name)
        still_needed = sorted((kept_names - related_names) & referenced)
        if still_needed:
            logger.info("Keeping providers a live scaleset still references: %s", still_needed)
        unrebuildable = referenced - kept_names - related_names
        if unrebuildable:
            logger.warning(
                "Scalesets reference providers that are no longer published and cannot be"
                " rebuilt from relation data: %s. Their teardown cannot complete until the"
                " owning configurator is related again.",
                sorted(unrebuildable),
            )
        return sorted(kept, key=lambda config: config["unit_name"])

    def _save_provider_record(self, published: list[dict[str, str]]) -> None:
        """Record the provider set GARM is running with, so it outlives the pod.

        Leader-only: this is the single writer, so the record has one revision history.

        Args:
            published: The provider configs the workload was started with.

        Raises:
            ProviderRecordError: If the record cannot be written. The hook stops rather than
                leave GARM running with providers the next restart could no longer retain.
        """
        if not self.unit.is_leader():
            return
        payload = json.dumps(published, sort_keys=True, separators=(",", ":"))
        try:
            try:
                secret = self.model.get_secret(label=GARM_PROVIDERS_LABEL)
            except ops.SecretNotFoundError:
                self.app.add_secret(
                    {GARM_PROVIDERS_SECRET_KEY: payload},
                    label=GARM_PROVIDERS_LABEL,
                    description="Provider set GARM was last started with",
                )
                return
            if secret.peek_content().get(GARM_PROVIDERS_SECRET_KEY) != payload:
                secret.set_content({GARM_PROVIDERS_SECRET_KEY: payload})
        except ops.ModelError as exc:
            raise ProviderRecordError(f"cannot record the GARM provider set: {exc}") from exc

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
            owasp_log.sys_startup(
                userid=username,
                description="GARM completed first-run initialisation",
            )
        except GarmApiError as exc:
            logger.warning("GARM first-run check failed (error out for retry): %s", exc)
            raise

    def _build_desired_scalesets(self, template_id: int | None) -> list[ScalesetSpec]:
        """Build the desired scaleset list from all garm-configurator relation units."""
        specs = []
        for relation in self.model.relations.get(GARM_CONFIGURATOR_RELATION_NAME, []):
            # Sorted, because `relation.units` is a set: the reconciler's dedupe is
            # first-wins, so an unstable order lets the winning spec flip between hooks.
            # A flip now changes the target scaleset name, which would create a
            # replacement and retire the live one on every flip.
            for unit in sorted(relation.units, key=lambda unit: unit.name):
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
            enable_shell=data.get("enable_shell", "") == "true",
            pre_install_scripts=_parse_pre_install_scripts(data.get("pre_install_scripts", "")),
            template_id=template_id,
            runner_config=RunnerConfig.from_databag(data),
            image_visibility=data.get("image_visibility", "").strip(),
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
            # Sorted for the same reason as `_build_desired_scalesets`: the dedupe
            # below is first-wins over an unordered set.
            for unit in sorted(relation.units, key=lambda unit: unit.name):
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

    def _reconcile_runners(self) -> list[ScaleSet] | None:
        """Sync GARM controller URLs, GitHub credentials, entities, then scalesets.

        The steps are ordered, not independent: GARM rejects every operational call with
        409 ``urls_required`` until the controller URLs are set; org/repo entities reference a
        credential by name; and scalesets are created under a registered entity. So a single
        authenticated client configures the URLs and reconciles credentials, then entities,
        then scalesets. The ``github_linux_charmed`` template is ensured before scalesets so each
        scaleset can reference it.

        Returns:
            The scalesets GARM still holds after the pass, or None when the pass could not
            run — no admin credentials, a connection or authorization failure, or a template
            that could not be applied. None means "unknown", and the caller must read it as
            "drop nothing".
        """
        admin_creds = self._get_admin_credentials()
        if not admin_creds:
            logger.warning("Admin credentials not yet available; deferring reconcile")
            return None

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
            # then scalesets — each dependency before its dependants. The garm-agent binaries are
            # published before the entities that switch agent mode on, because an entity in agent
            # mode and no matching binary stored makes GARM fall back to handing the runner a
            # github.com download URL.
            self._ensure_controller_urls(auth_client)
            agent_mode = self._ensure_agent_tools(auth_client)
            GithubReconciler(auth_client).reconcile(self._build_desired_credentials())
            EntityReconciler(auth_client, agent_mode).reconcile(charm_state.desired_entities)
            template_id = _apply_garm_template(auth_client, charm_state.ssh_debug_connections)
            replacing, surviving_scalesets = ScalesetReconciler(auth_client).reconcile(
                self._build_desired_scalesets(template_id)
            )
            # A label change recreates the scaleset and drains the old one, which
            # outlives this hook: report progress and let update-status converge it.
            # Active, not maintenance: every label is served throughout the drain, by
            # the replacement or the predecessor, so nothing is degraded. A drain can
            # run to DRAIN_DEADLINE, and blocking `juju wait-for` on hours of healthy
            # background convergence would be wrong.
            if replacing:
                self.update_app_and_unit_status(
                    ops.ActiveStatus(_scaleset_replacement_status(replacing))
                )
            else:
                self.update_app_and_unit_status(ops.ActiveStatus())
            return surviving_scalesets
        except CharmedTemplateError as exc:
            logger.warning("GARM charmed template error during reconcile: %s", exc)
            self.update_app_and_unit_status(ops.WaitingStatus(str(exc)))
            return None
        except GarmApiError as exc:
            logger.warning("GARM API error during reconcile: %s", exc)
            self.update_app_and_unit_status(ops.WaitingStatus("GARM sync failed"))
            return None

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
            agent_url=f"{base}/agent",
            allow_insecure_agent=not base.startswith("https://"),
        )

    def _ensure_agent_tools(self, auth_client: GarmAuthenticatedClient) -> bool | None:
        """Publish the rock's garm-agent binaries to GARM.

        Args:
            auth_client: Authenticated GARM API client.

        Returns:
            True once every architecture GARM can serve is published, so agent mode is
            safe to enable. None when the binaries could not be read at all, which leaves
            agent mode as it stands rather than flapping it off and on again.

        Raises:
            GarmApiError: If GARM rejects the upload. The caller waits and retries, which
                keeps agent mode off on a fresh deployment and unchanged on an existing
                one, rather than enabling it against a store that lacks a binary.
        """
        try:
            version = ensure_agent_tools(auth_client, self.unit.get_container(CONTAINER_NAME))
        except AgentToolsError as exc:
            logger.warning("garm-agent binaries unavailable in the workload: %s", exc)
            return None
        logger.info("GARM agent mode enabled with garm-agent %s from the rock", version)
        return True


def _scaleset_replacement_status(replacing: list[ScalesetProgress]) -> str:
    """Summarise in-progress scaleset replacements for the unit status.

    Args:
        replacing: Scaleset replacements still in flight, one entry per generation
            being replaced.

    Returns:
        A status message naming at most two scalesets, so it stays readable when
        several are replaced at once. Each is named by the logical name the operator
        configured — the live names carry a label hash the operator never chose — and
        the live names are logged in full by the reconciler. A scaleset draining two
        generations at once is named once, so it cannot push the others out of the
        message with a repeated line.
    """
    by_scaleset: dict[str, list[ScalesetProgress]] = {}
    for progress in replacing:
        by_scaleset.setdefault(progress.logical_name, []).append(progress)
    shown = [
        f"{logical_name} -> {entries[0].replacement_name} ({_scaleset_replacement_phase(entries)})"
        for logical_name, entries in list(by_scaleset.items())[:_MAX_DRAINING_IN_STATUS]
    ]
    remainder = len(by_scaleset) - len(shown)
    if remainder > 0:
        shown.append(f"+{remainder} more")
    return f"Replacing scaleset {', '.join(shown)}"


def _scaleset_replacement_phase(entries: list[ScalesetProgress]) -> str:
    """Describe where one scaleset's replacement has got to.

    Args:
        entries: Every generation of one scaleset still being replaced. A label change
            during an earlier drain leaves several predecessors handing over to the same
            replacement; to the operator that is one changeover, so they collapse into
            one phase — the least advanced, with the runner counts summed.

    Returns:
        The phase, in the operator's terms. The runner count is only reported once
        the labels have been handed over, since before that nothing is draining yet;
        with the count at zero the scaleset has drained and GARM has yet to accept
        its deletion, which is a distinct thing to be waiting on.
    """
    handovers = {entry.handover for entry in entries}
    if Handover.PENDING in handovers:
        return _PHASE_CREATING
    if Handover.FAILED in handovers:
        return _PHASE_RETIRING
    runners = sum(entry.remaining_runners for entry in entries)
    if not runners:
        return _PHASE_AWAITING_DELETION
    return f"draining {runners} runner{'' if runners == 1 else 's'}"


if __name__ == "__main__":
    ops.main(GarmCharm)
