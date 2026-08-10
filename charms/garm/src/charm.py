#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import dataclasses
import json
import logging
import secrets
import string
import typing

import ops
import paas_charm.go
from charm_state import (
    DEBUG_SSH_INTEGRATION_NAME,
    GARM_CONFIGURATOR_RELATION_NAME,
    CharmState,
    RunnerConfig,
    credential_name,
)
from entity_reconciler import EntityReconciler
from garm_api import GarmApiClient, GarmApiError, GarmAuthenticatedClient
from garm_template import CharmedTemplateError
from garm_template import apply_charmed_template as _apply_garm_template
from github_reconciler import (
    DEFAULT_GITHUB_ENDPOINT,
    MANAGED_CREDENTIAL_DESCRIPTION,
    CredentialSpec,
    GithubReconciler,
)
from paas_charm.app import App, WorkloadConfig
from paas_charm.charm_state import CharmState as PaasCharmState
from paas_charm.charm_utils import block_if_invalid_data
from paas_charm.database_migration import DatabaseMigration
from scaleset_reconciler import ScalesetReconciler, ScalesetSpec

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: typing.Final[str] = "/etc/garm/config.toml"
GARM_PROVIDER_CONFIG_DIR: typing.Final[str] = "/etc/garm"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
GARM_ADMIN_CREDENTIALS_LABEL: typing.Final[str] = "garm-admin-credentials"
CONTAINER_NAME: typing.Final[str] = "app"
SERVICE_NAME: typing.Final[str] = "go"


GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_PORT: typing.Final[int] = 8080
GARM_LISTEN_ADDRESS: typing.Final[str] = "0.0.0.0"
_DB_PASSPHRASE_LENGTH: typing.Final[int] = 32

GARM_CONFIG_VERSION: typing.Final[str] = "1"


@dataclasses.dataclass(frozen=True)
class ComputeState:
    """Desired workload state derived from the charm.

    This is a charm-side abstraction that mirrors the planned paas-charm
    ``_compute_state`` return shape. When paas-charm gains native support for
    this pattern, the charm can drop its custom App subclass and file-pushing
    logic and return this object directly.

    Attributes:
        env: Environment variables to inject into the workload service.

    """

    env: dict[str, str]


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


class GarmApp(App):
    """GARM-specific application manager.

    Bridges the charm-side ``ComputeState`` to the paas-charm 12-factor
    machinery. Injects GARM-specific environment variables and points the
    Pebble service at the entrypoint script.
    """

    def __init__(
        self,
        *,
        container: ops.Container,
        charm_state: PaasCharmState,
        workload_config: WorkloadConfig,
        database_migration: DatabaseMigration,
        compute_state: ComputeState,
    ) -> None:
        """Initialize the GARM application manager.

        Args:
            container: the application container.
            charm_state: the paas-charm state instance.
            workload_config: the workload configuration.
            database_migration: the database migration manager.
            compute_state: the desired GARM state to apply.
        """
        super().__init__(
            container=container,
            charm_state=charm_state,
            workload_config=workload_config,
            database_migration=database_migration,
        )
        self._compute_state = compute_state
        self._alternate_service_command = "/usr/local/bin/garm-entrypoint.py"

    def gen_environment(self) -> dict[str, str]:
        """Generate environment variables for the GARM entrypoint.

        Returns:
            Merged dictionary of paas-charm framework env vars and GARM vars.
        """
        env = super().gen_environment()
        env.update(self._compute_state.env)
        return env

    def restart(self) -> None:
        """Apply the Pebble layer and delegate migration execution to paas-charm."""
        super().restart()


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

    @block_if_invalid_data
    def _reconcile(self, _: ops.EventBase) -> None:
        """Reconcile charm state."""
        self.restart()

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
        return dataclasses.replace(super()._workload_config, port=GARM_PORT, metrics_target=None)

    def _create_app(self, compute_state: ComputeState | None = None) -> GarmApp:
        """Create the GARM application manager.

        Args:
            compute_state: Previously computed workload state, when available.

        Returns:
            A ``GarmApp`` configured with the current ``ComputeState``.
        """
        if compute_state is None:
            # paas-charm calls _create_app() from is_ready() when it needs to
            # stop services for a blocked integration. Do not recompute GARM
            # relation state from that framework readiness path.
            compute_state = ComputeState(env={})
        return GarmApp(
            container=self._container,
            charm_state=self._create_charm_state(),
            workload_config=self._workload_config,
            database_migration=self._database_migration,
            compute_state=compute_state,
        )

    def restart(self, rerun_migrations: bool = False) -> None:
        """Write GARM config then restart the workload.

        Ensures secrets before the readiness gate so they exist on
        install/leader_elected before pebble is ready, then gates on
        workload readiness before writing config and replanning.

        Args:
            rerun_migrations: Passed through to the parent restart.
        """
        self._ensure_secrets()
        secrets_data = typing.cast(dict[str, str], self._get_secrets())

        if not self.is_ready():
            return

        self._warn_unsupported_port_options()

        compute_state = self._compute_state(secrets_data=secrets_data)

        # _compute_state sets the status and returns empty state when a required
        # input is unavailable.
        if not compute_state.env:
            return

        # Pebble compares the generated service environment and restarts only
        # when one of the actual configuration inputs changes.
        app = self._create_app(compute_state)
        # The framework's layer has to be laid down before ours. The first time it runs it
        # snapshots whatever services the plan already holds and republishes them from a layer
        # that takes precedence over ours, so a snapshot taken once our service exists pins that
        # service's environment — proxy values and config_hash alike — for the container's
        # lifetime, and no later change can reach the running workload.
        super().restart(rerun_migrations=rerun_migrations)
        app.restart()
        self._maybe_first_run()
        # Reconcile last: the framework's restart finishes by reporting active unconditionally,
        # which would bury the status a failed GARM sync reports here.
        self._reconcile_runners()

    def _compute_state(self, secrets_data: dict[str, str]) -> ComputeState:
        """Derive the desired workload state from Juju state.

        Returns a ``ComputeState`` containing the environment variables the
        GARM entrypoint needs and the provider configuration files to push.
        When paas-charm gains native ``_compute_state`` support, this data
        gathering can be returned directly and the ``GarmApp`` wrapper
        removed.

        Returns:
            The desired GARM workload state.
        """
        env: dict[str, str] = {}

        # PostgreSQL is supplied by paas-charm as POSTGRESQL_DB_* environment
        # variables. Keep those native names; the entrypoint consumes them directly.
        postgresql_config = self._get_postgresql_config()
        if not postgresql_config:
            # paas_charm.is_ready() already blocks on a missing required relation,
            # but a joined relation may not yet carry data. Return empty state so
            # no incomplete config reaches the workload.
            logger.info("PostgreSQL relation data not yet available; waiting")
            self.update_app_and_unit_status(ops.WaitingStatus("Waiting for postgresql relation"))
            return ComputeState(env={})

        provider_configs = self._get_configurator_provider_configs()
        if not provider_configs:
            # Empty configs don't distinguish a removed relation from one still
            # mid-publish, but only a removed relation orphans scalesets. Prune
            # them (via _reconcile_runners) only when the relation is truly gone;
            # reconciling mid-publish would delete live scalesets against an empty
            # desired state.
            if not CharmState.from_charm(self).configurator_related:
                logger.warning(
                    "Pausing GARM reconciliation: waiting for garm-configurator relation"
                )
                self._reconcile_runners()
            self.update_app_and_unit_status(
                ops.WaitingStatus("Waiting for garm-configurator data")
            )
            return ComputeState(env={})

        env["GARM_JWT_SECRET"] = secrets_data["jwt-secret"]
        env["GARM_PASSPHRASE"] = secrets_data["db-passphrase"]

        # Provider configuration is passed as one canonical environment value;
        # the entrypoint owns rendering config.toml and provider files.
        env["GARM_PROVIDERS_JSON"] = json.dumps(
            provider_configs, sort_keys=True, separators=(",", ":")
        )

        env["GARM_CONFIG_VERSION"] = GARM_CONFIG_VERSION
        return ComputeState(env=env)

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
            return []

        configs: list[dict[str, str]] = []
        for unit in relation.units:
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
        except ops.SecretNotFoundError:
            logger.warning("Secret %s is not accessible", secret_uri)
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

        client = GarmApiClient(f"http://127.0.0.1:{GARM_PORT}/api/v1")

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
                data = relation.data[unit]
                name = data.get("name", "")
                if not name:
                    continue

                org = data.get("org", "")
                repo = data.get("repo", "")
                if org:
                    entity_type = "organization"
                    entity_name = org
                elif repo:
                    entity_type = "repository"
                    entity_name = repo
                else:
                    logger.warning("Skipping scaleset %s: neither org nor repo specified", name)
                    continue

                required = {
                    "provider_name": data.get("provider_name", ""),
                    "image": data.get("image_id", ""),
                    "flavor": data.get("flavor", ""),
                    "os_arch": data.get("os_arch", ""),
                    "max_runner": data.get("max_runner", ""),
                }
                missing = [k for k, v in required.items() if not v]
                if missing:
                    logger.warning(
                        "Skipping scaleset %s: missing required fields %s",
                        name,
                        missing,
                    )
                    continue
                try:
                    min_idle = int(data.get("min_idle_runner", "0"))
                    max_runners = int(required["max_runner"])
                except ValueError:
                    continue
                specs.append(
                    ScalesetSpec(
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
                        labels=[
                            label.strip()
                            for label in data.get("labels", "").split(",")
                            if label.strip()
                        ],
                        runner_group=data.get("runner_group", ""),
                        pre_install_scripts=_parse_pre_install_scripts(
                            data.get("pre_install_scripts", "")
                        ),
                        template_id=template_id,
                        runner_config=RunnerConfig.from_databag(data),
                    )
                )
        return specs

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
                data = relation.data[unit]
                app_id_raw = data.get("github_app_id", "")
                installation_id_raw = data.get("github_installation_id", "")
                key_secret_uri = data.get("github_private_key_secret_uri", "")
                if not (app_id_raw and installation_id_raw and key_secret_uri):
                    continue
                try:
                    app_id = int(app_id_raw)
                    installation_id = int(installation_id_raw)
                except ValueError:
                    logger.warning(
                        "Skipping GitHub credential from %s: non-numeric app/installation id "
                        "(app_id=%r, installation_id=%r)",
                        unit.name,
                        app_id_raw,
                        installation_id_raw,
                    )
                    continue

                dedupe_key = (app_id, installation_id)
                if dedupe_key in credentials:
                    continue

                private_key = self._resolve_secret_value(str(key_secret_uri))
                if not private_key:
                    logger.warning(
                        "Skipping GitHub credential for app %s: private key secret unavailable",
                        app_id,
                    )
                    continue

                credentials[dedupe_key] = CredentialSpec(
                    name=credential_name(app_id, installation_id),
                    endpoint=DEFAULT_GITHUB_ENDPOINT,
                    app_id=app_id,
                    installation_id=installation_id,
                    private_key=private_key,
                    description=MANAGED_CREDENTIAL_DESCRIPTION,
                )

        return list(credentials.values())

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
        base_url = f"http://127.0.0.1:{GARM_PORT}/api/v1"
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
