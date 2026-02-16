#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import dataclasses
import json
import logging
import pathlib
import typing

import ops
import paas_charm.go
from planner import PlannerClient, PlannerError

logger = logging.getLogger(__name__)


HTTP_PORT: typing.Final[int] = 8080
PLANNER_RELATION_NAME: typing.Final[str] = "planner"
ADMIN_TOKEN_CONFIG_NAME: typing.Final[str] = "admin-token"
MANAGED_FLAVOR_SECRET_KEY: typing.Final[str] = "managed-flavor"
PLANNER_FLAVOR_RELATION_KEY: typing.Final[str] = "flavor"
PLANNER_LABELS_RELATION_KEY: typing.Final[str] = "labels"
PLANNER_PLATFORM_RELATION_KEY: typing.Final[str] = "platform"
PLANNER_PRIORITY_RELATION_KEY: typing.Final[str] = "priority"
PLANNER_MINIMUM_PRESSURE_RELATION_KEY: typing.Final[str] = "minimum-pressure"
DEFAULT_FLAVOR_PLATFORM: typing.Final[str] = "github"
DEFAULT_FLAVOR_LABELS: typing.Final[list[str]] = ["self-hosted"]
DEFAULT_FLAVOR_PRIORITY: typing.Final[int] = 50
DEFAULT_FLAVOR_MINIMUM_PRESSURE: typing.Final[int] = 0


class ConfigError(Exception):
    """Error for configuration issues."""


class JujuError(Exception):
    """Error for Juju-related issues."""


class GithubRunnerPlannerCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.enable_flavor_action, self._on_enable_flavor_action)
        self.framework.observe(self.on.disable_flavor_action, self._on_disable_flavor_action)

        self.framework.observe(
            self.on[PLANNER_RELATION_NAME].relation_changed,
            self._on_manager_relation_changed,
        )
        self.framework.observe(
            self.on[PLANNER_RELATION_NAME].relation_broken,
            self._on_planner_relation_broken,
        )

    def get_cos_dir(self) -> str:
        """Get the COS directory for this charm.

        Returns:
            The COS directory.
        """
        return str((pathlib.Path(__file__).parent / "cos").absolute())

    def _create_app(self):
        """Patch _create_app to add OpenTelemetry environment variables."""
        original_app = super()._create_app()
        charm = self

        def gen_environment() -> dict[str, str]:
            env = original_app.gen_environment()
            env["OTEL_METRICS_EXPORTER"] = "prometheus"
            env["OTEL_EXPORTER_PROMETHEUS_HOST"] = "0.0.0.0"
            env["OTEL_EXPORTER_PROMETHEUS_PORT"] = str(charm.config.get("metrics-port"))
            env["OTEL_LOGS_EXPORTER"] = "console"
            if env.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
                traces_endpoint = env["OTEL_EXPORTER_OTLP_ENDPOINT"]
                env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = (
                    traces_endpoint.removesuffix("/") + "/v1/traces"
                )
                del env["OTEL_EXPORTER_OTLP_ENDPOINT"]
                env["OTEL_TRACES_EXPORTER"] = "otlp"
                env["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] = "http/protobuf"
            return env

        app = super()._create_app()
        setattr(app, "gen_environment", gen_environment)
        return app

    def _create_planner_client(self) -> PlannerClient:
        """Create a planner client instance.

        Returns:
            PlannerClient instance.
        """
        admin_token = self._get_admin_token()
        env = self._gen_environment()
        port = env.get("APP_PORT", "8080")
        base_url = f"http://127.0.0.1:{port}"
        return PlannerClient(base_url=base_url, admin_token=admin_token)

    def _on_enable_flavor_action(self, event: ops.ActionEvent) -> None:
        """Handle the enable-flavor action.

        Args:
            event: The action event.
        """
        flavor = event.params["flavor"]
        try:
            client = self._create_planner_client()
            client.update_flavor(flavor_name=flavor, is_disabled=False)
            event.set_results({"message": f"Flavor '{flavor}' enabled successfully"})
        except (ConfigError, PlannerError) as e:
            error_msg = str(e)
            event.fail(error_msg)
            logger.error("Failed to enable flavor %s: %s", flavor, error_msg)

    def _on_disable_flavor_action(self, event: ops.ActionEvent) -> None:
        """Handle the disable-flavor action.

        Args:
            event: The action event.
        """
        flavor = event.params["flavor"]
        try:
            client = self._create_planner_client()
            client.update_flavor(flavor_name=flavor, is_disabled=True)
            event.set_results({"message": f"Flavor '{flavor}' disabled successfully"})
        except (ConfigError, PlannerError) as e:
            error_msg = str(e)
            event.fail(error_msg)
            logger.error("Failed to disable flavor %s: %s", flavor, error_msg)

    def _on_manager_relation_changed(self, _: ops.RelationChangedEvent) -> None:
        """Handle changes to the github-runner-manager relation."""
        self._setup()

    def _on_planner_relation_broken(self, event: ops.RelationBrokenEvent) -> None:
        """Handle planner relation broken events."""
        self._setup(broken_relation_id=event.relation.id)

    def _setup(self, broken_relation_id: int | None = None) -> None:
        """Set up the planner application."""
        self.unit.status = ops.MaintenanceStatus("Setting up planner application")
        try:
            client = self._create_planner_client()
        except ConfigError:
            logger.exception("Missing %s configuration", ADMIN_TOKEN_CONFIG_NAME)
            self.unit.status = ops.BlockedStatus(
                f"Missing {ADMIN_TOKEN_CONFIG_NAME} configuration"
            )
            return

        self.unit.status = ops.MaintenanceStatus("Setup planner integrations")
        self._setup_planner_relation(client=client, broken_relation_id=broken_relation_id)
        self.unit.status = ops.ActiveStatus()

    def _setup_planner_relation(
        self, client: PlannerClient, broken_relation_id: int | None = None
    ) -> None:
        """Setup the planner relations if this unit is the leader.

        During relation_broken, Juju still lists the broken relation among
        the active relations. Passing its ID via broken_relation_id excludes
        it from reconciliation so its resources are cleaned up as orphans.
        """
        if not self.unit.is_leader():
            return

        all_token_names = client.list_auth_token_names()
        auth_token_names = [
            token for token in all_token_names if self._check_name_fit_auth_token(token)
        ]
        existing_tokens = set(auth_token_names)
        reconciled = set()

        relations = self.model.relations[PLANNER_RELATION_NAME]
        for relation in relations:
            if relation.id == broken_relation_id:
                continue
            auth_token_name = self._get_auth_token_name(relation.id)
            try:
                if auth_token_name not in existing_tokens:
                    self._create_and_share_relation_secret(
                        client=client,
                        relation=relation,
                        auth_token_name=auth_token_name,
                    )
                self._sync_relation_flavor_secret(
                    client=client, relation=relation, auth_token_name=auth_token_name
                )
            except (PlannerError, JujuError):
                logger.exception(
                    "Failed to reconcile relation %s, skipping", relation.id
                )
            finally:
                reconciled.add(auth_token_name)

        # Clean up tokens, flavors, and secrets that have no active relation.
        # Only tokens that were successfully reconciled are excluded.
        orphaned = existing_tokens - reconciled
        for token_name in orphaned:
            self._cleanup_orphaned_relation_resources(client=client, token_name=token_name)

    def _create_and_share_relation_secret(
        self,
        client: PlannerClient,
        relation: ops.Relation,
        auth_token_name: str,
    ) -> None:
        """Create auth token and relation secret, then share relation connection data."""
        auth_token = client.create_auth_token(auth_token_name)
        try:
            secret = self.app.add_secret({"token": auth_token}, label=auth_token_name)
            secret.grant(relation)
        except ValueError as err:
            logger.exception("Failed to add secret for relation %d", relation.id)
            raise JujuError(
                f"Failed to create or grant secret for relation {relation.id}"
            ) from err
        except ops.hookcmds.Error as err:
            logger.exception("Failed to grant secret for relation %d", relation.id)
            raise JujuError(f"Failed to grant secret for relation {relation.id}") from err

        # The _base_url is set up by the parent class paas_charm.go.Charm.
        # It points to ingress URL if there is one, otherwise to the K8S service.
        relation.data[self.app]["endpoint"] = self._base_url
        relation.data[self.app]["token"] = secret.id

    def _cleanup_orphaned_relation_resources(self, client: PlannerClient, token_name: str) -> None:
        """Delete orphaned managed flavor, secret revisions, and auth token."""
        try:
            secret = self.model.get_secret(label=token_name)
            flavor_name = secret.get_content().get(MANAGED_FLAVOR_SECRET_KEY)
            if flavor_name:
                client.delete_flavor(flavor_name)
            secret.remove_all_revisions()
        except ops.SecretNotFoundError:
            # It is fine if the secret is already removed.
            logger.debug("Secret with label %s not found during cleanup", token_name)
        client.delete_auth_token(token_name)

    def _sync_relation_flavor_secret(
        self, client: PlannerClient, relation: ops.Relation, auth_token_name: str
    ) -> None:
        """Reconcile the managed flavor for a relation.

        The auth_token_name is used as the Juju secret label to look up the
        per-relation secret where the managed flavor name is tracked. This
        allows cleanup of the flavor when the relation is later removed.
        """
        flavor_config = RelationFlavorConfig.from_relation_data(relation.data[relation.app])
        try:
            secret = self.model.get_secret(label=auth_token_name)
        except ops.SecretNotFoundError:
            logger.warning("Secret %s not found, skipping flavor sync", auth_token_name)
            return
        secret_content = secret.get_content()
        existing_flavor = secret_content.get(MANAGED_FLAVOR_SECRET_KEY)

        if not flavor_config:
            if not existing_flavor:
                return
            client.delete_flavor(existing_flavor)
            secret_content.pop(MANAGED_FLAVOR_SECRET_KEY)
            secret.set_content(secret_content)
            return

        if self._flavor_matches(client, flavor_config, existing_flavor):
            return

        # Delete the old flavor when the name or config has changed,
        # since create_flavor does not update existing flavors.
        if existing_flavor:
            client.delete_flavor(existing_flavor)

        client.create_flavor(
            flavor_name=flavor_config.name,
            platform=flavor_config.platform,
            labels=flavor_config.labels,
            priority=flavor_config.priority,
            minimum_pressure=flavor_config.minimum_pressure,
        )

        if existing_flavor == flavor_config.name:
            return
        secret_content[MANAGED_FLAVOR_SECRET_KEY] = flavor_config.name
        secret.set_content(secret_content)

    @staticmethod
    def _flavor_matches(
        client: PlannerClient,
        desired: "RelationFlavorConfig",
        existing_flavor_name: str | None,
    ) -> bool:
        """Check whether the existing planner flavor already matches the desired config."""
        if existing_flavor_name != desired.name:
            return False
        existing = client.get_flavor(desired.name)
        if existing is None:
            return False
        return (
            existing.platform == desired.platform
            and existing.labels == desired.labels
            and existing.priority == desired.priority
            and existing.minimum_pressure == desired.minimum_pressure
        )

    def _get_admin_token(self) -> str:
        admin_token_secret_id = self.config.get(ADMIN_TOKEN_CONFIG_NAME)
        if not admin_token_secret_id:
            raise ConfigError(f"{ADMIN_TOKEN_CONFIG_NAME} config value is not set")
        admin_token_secret = self.model.get_secret(id=admin_token_secret_id)
        return admin_token_secret.get_content()["value"]

    @staticmethod
    def _get_auth_token_name(relation_id: int) -> str:
        """Build the auth token name based on relation ID.

        Args:
            relation_id: The relation ID.

        Returns:
            The auth token name.
        """
        return f"relation-{relation_id}"

    @staticmethod
    def _check_name_fit_auth_token(name: str) -> bool:
        """Check if the name fits the auth token naming requirements.

        Args:
            name: The name to check.

        Returns:
            True if the name fits the requirements, False otherwise.
        """
        return name.startswith("relation-")


@dataclasses.dataclass(frozen=True)
class RelationFlavorConfig:
    """Flavor configuration parsed from relation data."""

    name: str
    platform: str
    labels: list[str]
    priority: int
    minimum_pressure: int

    @classmethod
    def from_relation_data(
        cls, relation_data: typing.Mapping[str, str]
    ) -> "RelationFlavorConfig | None":
        """Parse flavor config from relation data.

        Args:
            relation_data: The relation data mapping (string keys and values).

        Returns:
            A RelationFlavorConfig if a flavor name is set, None otherwise.
        """
        flavor_name = relation_data.get(PLANNER_FLAVOR_RELATION_KEY)
        if not flavor_name:
            return None
        return cls(
            name=flavor_name,
            # The planner API only supports "github" as platform for now.
            platform=DEFAULT_FLAVOR_PLATFORM,
            labels=_parse_relation_labels(relation_data.get(PLANNER_LABELS_RELATION_KEY)),
            priority=_parse_relation_int(
                relation_data.get(PLANNER_PRIORITY_RELATION_KEY),
                PLANNER_PRIORITY_RELATION_KEY,
                default=DEFAULT_FLAVOR_PRIORITY,
            ),
            minimum_pressure=_parse_relation_int(
                relation_data.get(PLANNER_MINIMUM_PRESSURE_RELATION_KEY),
                PLANNER_MINIMUM_PRESSURE_RELATION_KEY,
                default=DEFAULT_FLAVOR_MINIMUM_PRESSURE,
            ),
        )


def _parse_relation_labels(raw_labels: str | None) -> list[str]:
    """Parse relation labels field from JSON array or comma-separated string."""
    if not raw_labels:
        return list(DEFAULT_FLAVOR_LABELS)
    try:
        parsed = json.loads(raw_labels)
        if isinstance(parsed, list) and all(isinstance(label, str) for label in parsed):
            return parsed
    except json.JSONDecodeError:
        pass
    labels = [item.strip() for item in raw_labels.split(",") if item.strip()]
    return labels if labels else list(DEFAULT_FLAVOR_LABELS)


def _parse_relation_int(value: str | None, field_name: str, default: int) -> int:
    """Parse integer relation field, returning default when unset."""
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as err:
        raise JujuError(f"Invalid {field_name} value {value!r}") from err


if __name__ == "__main__":
    ops.main(GithubRunnerPlannerCharm)
