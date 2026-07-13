#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm entrypoint."""

import dataclasses
import hashlib
import json
import logging
import os
import secrets
import string
import typing

import ops
import paas_charm.go
import tomli_w
import yaml
from paas_charm.app import WorkloadConfig
from paas_charm.charm_utils import block_if_invalid_data

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
from scaleset_reconciler import ScalesetReconciler, ScalesetSpec

logger = logging.getLogger(__name__)

GARM_CONFIG_PATH: typing.Final[str] = "/etc/garm/config.toml"
GARM_PROVIDER_CONFIG_DIR: typing.Final[str] = "/etc/garm"
GARM_SECRETS_LABEL: typing.Final[str] = "garm-secrets"
GARM_ADMIN_CREDENTIALS_LABEL: typing.Final[str] = "garm-admin-credentials"
CONTAINER_NAME: typing.Final[str] = "app"
PEBBLE_SERVICE_NAME: typing.Final[str] = "app"
GARM_BINARY: typing.Final[str] = "/usr/local/bin/garm"
OPENSTACK_PROVIDER_BINARY: typing.Final[str] = "/usr/local/bin/garm-provider-openstack"
GARM_PORT: typing.Final[int] = 8080
GARM_LISTEN_ADDRESS: typing.Final[str] = "0.0.0.0"
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


# Juju injects model proxy config (juju-http-proxy/...) into the hook
# environment as JUJU_CHARM_*. GARM and its child provider executables
# (garm-provider-openstack -> gophercloud) honour the conventional proxy
# variables, so we mirror each configured value into both the lower- and
# upper-case form.
_JUJU_PROXY_VARS: typing.Final[dict[str, str]] = {
    "JUJU_CHARM_HTTP_PROXY": "http_proxy",
    "JUJU_CHARM_HTTPS_PROXY": "https_proxy",
    "JUJU_CHARM_NO_PROXY": "no_proxy",
}


def _proxy_environment() -> dict[str, str]:
    """Build proxy env vars from Juju model proxy config.

    Returns a mapping with both lower- and upper-case variants for each
    non-empty Juju proxy setting, suitable for a Pebble service environment.
    """
    env: dict[str, str] = {}
    for juju_var, target in _JUJU_PROXY_VARS.items():
        value = os.environ.get(juju_var, "").strip()
        if value:
            env[target] = value
            env[target.upper()] = value
    return env


def _build_provider_list(
    providers: list[dict[str, str]] | None,
    proxy_var_names: list[str] | None = None,
) -> tuple[list[dict[str, typing.Any]], dict[str, str]]:
    r"""Build the list of [[provider]] TOML entries and provider config files.

    The garm-provider-openstack binary reads its credentials from a
    provider-specific TOML config file that references a clouds.yaml file
    -- it does NOT read OPENSTACK_* environment variables.

    This function generates both the GARM provider entries and the
    provider config file contents that must be pushed to the container.

    Args:
        providers: List of provider config dicts from Configurator units,
            each with keys: unit_name, auth_url, username, password,
            project_name, user_domain_name, project_domain_name,
            region_name, network.
        proxy_var_names: Optional list of environment variable names to
            whitelist in each provider's ``external.environment_variables``
            so GARM forwards them to the child provider process. When None
            or empty, the key is omitted (preserving existing behaviour).

    Returns:
        A tuple of (provider_entries, provider_files):
        - provider_entries: List of provider dicts for the GARM TOML
          [[provider]] section, with config_file paths set.
        - provider_files: Dict mapping container file paths to their
          contents (provider TOML + clouds.yaml for each provider).
    """
    if not providers:
        return [
            {
                "name": "openstack",
                "provider_type": "external",
                "description": "OpenStack provider",
                "external": _build_external_block("", proxy_var_names),
            }
        ], {}

    result: list[dict[str, typing.Any]] = []
    provider_files: dict[str, str] = {}

    for provider in providers:
        unit_name = provider["unit_name"]

        provider_toml_path = f"{GARM_PROVIDER_CONFIG_DIR}/provider-{unit_name}.toml"
        clouds_yaml_path = f"{GARM_PROVIDER_CONFIG_DIR}/clouds-{unit_name}.yaml"

        # Build the provider-specific TOML config that garm-provider-openstack reads.
        provider_toml = tomli_w.dumps(
            {
                "cloud": unit_name,
                "network_id": provider["network"],
                "credentials": {
                    "clouds": clouds_yaml_path,
                },
                # 2025/07/24 - This option is set to mitigate CVE-2024-6174
                "use_config_drive": True,
            }
        )

        # Build the clouds.yaml that gophercloud reads for OpenStack credentials.
        auth_block = {
            "auth_url": provider["auth_url"],
            "username": provider["username"],
            "password": provider["password"],
            "project_name": provider["project_name"],
            "user_domain_name": provider["user_domain_name"],
            "project_domain_name": provider["project_domain_name"],
        }

        clouds_yaml = _render_clouds_yaml(unit_name, auth_block, provider["region_name"])

        provider_files[provider_toml_path] = provider_toml
        provider_files[clouds_yaml_path] = clouds_yaml

        result.append(
            {
                "name": unit_name,
                "provider_type": "external",
                "description": f"OpenStack provider ({unit_name})",
                "external": _build_external_block(provider_toml_path, proxy_var_names),
            }
        )
    return result, provider_files


def _build_external_block(
    config_file: str, proxy_var_names: list[str] | None
) -> dict[str, typing.Any]:
    """Build a provider ``external`` block, whitelisting proxy vars when set.

    Args:
        config_file: Path to the provider-specific TOML config file.
        proxy_var_names: Optional environment variable names to forward to the
            child provider process. When None or empty, the key is omitted.

    Returns:
        The ``external`` dict for a GARM [[provider]] entry.
    """
    external: dict[str, typing.Any] = {
        "config_file": config_file,
        "provider_executable": OPENSTACK_PROVIDER_BINARY,
    }
    if proxy_var_names:
        external["environment_variables"] = proxy_var_names
    return external


def _render_clouds_yaml(cloud_name: str, auth: dict[str, str], region_name: str) -> str:
    """Render a minimal clouds.yaml for gophercloud using PyYAML.

    Args:
        cloud_name: The cloud name in the ``clouds`` dict.
        auth: Auth parameters (auth_url, username, password, project_name,
            user_domain_name, project_domain_name).
        region_name: OpenStack region name.

    Returns:
        YAML-formatted string.
    """
    clouds = {
        "clouds": {
            cloud_name: {
                "auth": auth,
                "region_name": region_name,
            }
        }
    }
    return yaml.dump(clouds, default_flow_style=False)


def render_garm_toml(
    *,
    jwt_secret: str,
    db_passphrase: str,
    postgresql_config: dict[str, typing.Any],
    providers: list[dict[str, str]] | None = None,
    proxy_var_names: list[str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Render GARM's TOML configuration file content.

    Args:
        jwt_secret: Secret string used to sign GARM JWT tokens.
        db_passphrase: 32-character passphrase for AES-256 encryption of secrets in the DB.
        postgresql_config: PostgreSQL connection parameters (username, password,
            hostname, port, database, sslmode).
        providers: Optional list of provider config dicts from Configurator
            units. If None or empty, a default single "openstack" provider
            is used for backward compatibility.
        proxy_var_names: Optional list of environment variable names to
            whitelist in each provider's ``external.environment_variables``
            so GARM forwards them to child provider processes. When None
            or empty, the key is omitted from the provider entries.

    Returns:
        A tuple of (toml_content, provider_files):
        - toml_content: TOML-formatted string ready to be written to disk.
        - provider_files: Dict mapping container file paths to their
          contents (provider config TOML + clouds.yaml for each provider).
    """
    provider_entries, provider_files = _build_provider_list(providers, proxy_var_names)
    config: dict[str, typing.Any] = {
        "database": {
            "backend": "postgresql",
            "passphrase": db_passphrase,
            "postgresql": postgresql_config,
        },
        "apiserver": {
            "bind": GARM_LISTEN_ADDRESS,
            "port": GARM_PORT,
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
        "provider": provider_entries,
    }
    return tomli_w.dumps(config), provider_files


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

    def restart(self, rerun_migrations: bool = False) -> None:
        """Write GARM config then restart the workload.

        Ensures secrets before the readiness gate so they exist on
        install/leader_elected before pebble is ready, then gates on
        workload readiness before writing config and replanning.

        Args:
            rerun_migrations: Passed through to the parent restart.
        """
        self._ensure_secrets()

        if not self.is_ready():
            return

        self._warn_unsupported_port_options()

        # Short-circuit if postgresql relation data is not yet available.
        # GARM cannot start without a database connection.
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
            # Empty configs don't distinguish a removed relation from one still
            # mid-publish, but only a removed relation orphans scalesets. Prune
            # them (via _reconcile_runners) only when the relation is truly gone;
            # reconciling mid-publish would delete live scalesets against an empty
            # desired state.
            if not CharmState.from_charm(self).configurator_related:
                self._reconcile_runners()
            self.update_app_and_unit_status(
                ops.WaitingStatus("Waiting for garm-configurator relation")
            )
            return

        proxy_env = _proxy_environment()
        toml_content, provider_files = render_garm_toml(
            jwt_secret=secrets_data["jwt-secret"],
            db_passphrase=secrets_data["db-passphrase"],
            postgresql_config=postgresql_config,
            providers=provider_configs,
            proxy_var_names=sorted(proxy_env.keys()),
        )

        # Detect config changes by comparing the freshly rendered config hash against the
        # config_hash stored in the container's current Pebble plan. The proxy *values* live
        # only in the service environment, so they are folded into the hash input here; the
        # stored hash was computed from the same input last time, making the comparison
        # symmetric. This catches a proxy-value-only change (variable set unchanged) that the
        # TOML-embedded variable *names* alone would miss, and — by comparing against the
        # actual plan rather than the on-disk TOML — avoids the desync where a matching
        # on-disk file wedged the layer permanently.
        hash_input = (
            toml_content
            + "\n"
            + "\n".join(f"{path}\n{content}" for path, content in sorted(provider_files.items()))
        )
        # Only extend the input when a proxy is configured, so the no-proxy hash matches
        # earlier charm revisions and upgrading doesn't force a spurious one-time replan.
        if proxy_env:
            hash_input += "\n" + "\n".join(f"{k}={v}" for k, v in sorted(proxy_env.items()))
        new_hash = self._hash_toml(hash_input)

        container = self.unit.get_container(CONTAINER_NAME)
        previous_hash = self._current_config_hash(container)
        if previous_hash == new_hash:
            logger.debug(
                "Workload config (TOML, provider files, proxy env) unchanged; skipping replan"
            )
            self._reconcile_runners()
            return

        # Log non-sensitive metadata about the config change.
        # Do NOT log toml_content here — it contains secrets
        # (jwt_secret, db_passphrase, passwords).
        provider_names = [p.get("unit_name") for p in provider_configs]
        logger.info("Updating GARM config for providers: %s", provider_names)

        container.push(GARM_CONFIG_PATH, toml_content, permissions=0o600, make_dirs=True)
        for path, content in provider_files.items():
            container.push(path, content, permissions=0o600, make_dirs=True)

        container.add_layer(
            "garm-command",
            {
                "services": {
                    PEBBLE_SERVICE_NAME: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": f"{GARM_BINARY} -config {GARM_CONFIG_PATH}",
                        "environment": {
                            "config_hash": new_hash,
                            **proxy_env,
                        },
                    }
                }
            },
            combine=True,
        )
        container.replan()
        self._maybe_first_run()
        self._reconcile_runners()
        super().restart(rerun_migrations=rerun_migrations)

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

    @staticmethod
    def _hash_toml(toml_content: str) -> str:
        """Return the SHA-256 hex digest of the given TOML content.

        Args:
            toml_content: The TOML string to hash.

        Returns:
            A 64-character hex digest string.
        """
        return hashlib.sha256(toml_content.encode("utf-8")).hexdigest()

    @staticmethod
    def _current_config_hash(container: ops.Container) -> str | None:
        """Return the config_hash stored in the container's current Pebble plan.

        This is the config hash computed during the previous successful replan;
        it lives in the app service's environment. Returns None when the service
        (or the key) is absent, i.e. the container was never configured.

        Args:
            container: The workload container to read the plan from.

        Returns:
            The stored config_hash, or None if it has not been set yet.
        """
        service = container.get_plan().services.get(PEBBLE_SERVICE_NAME)
        if service is None:
            return None
        return service.environment.get("config_hash")

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
