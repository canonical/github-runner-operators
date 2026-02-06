#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

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
        self.framework.observe(
            self.on.enable_flavor_action, self._on_enable_flavor_action
        )
        self.framework.observe(
            self.on.disable_flavor_action, self._on_disable_flavor_action
        )

        self.framework.observe(
            self.on[PLANNER_RELATION_NAME].relation_changed,
            self._on_manager_relation_changed,
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
        except (ConfigError, PlannerError, RuntimeError) as e:
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
        except (ConfigError, PlannerError, RuntimeError) as e:
            error_msg = str(e)
            event.fail(error_msg)
            logger.error("Failed to disable flavor %s: %s", flavor, error_msg)

    def _on_manager_relation_changed(self, _: ops.RelationChangedEvent) -> None:
        """Handle changes to the github-runner-manager relation."""
        self._setup()

    def _setup(self) -> None:
        """Setup the planner application."""
        self.unit.status = ops.MaintenanceStatus("Setting up planner application")
        try:
            self._get_admin_token()
        except ConfigError:
            logger.exception("Missing %s configuration", ADMIN_TOKEN_CONFIG_NAME)
            self.unit.status = ops.BlockedStatus(
                f"Missing {ADMIN_TOKEN_CONFIG_NAME} configuration"
            )
            return

        self.unit.status = ops.MaintenanceStatus("Setup planner integrations")
        self._setup_planner_relation()
        self.unit.status = ops.ActiveStatus()

    def _setup_planner_relation(self) -> None:
        """Setup the planner relations if this unit is the leader."""
        if not self.unit.is_leader():
            return

        client = self._create_planner_client()
        all_token_names = client.list_auth_token_names()
        auth_token_names = [
            token for token in all_token_names if self._check_name_fit_auth_token(token)
        ]
        auth_token_set = set(auth_token_names)

        relations = self.model.relations[PLANNER_RELATION_NAME]
        for relation in relations:
            auth_token_name = self._get_auth_token_name(relation.id)
            if auth_token_name not in auth_token_set:
                auth_token = client.create_auth_token(auth_token_name)
                try:
                    secret = self.app.add_secret(
                        {"token": auth_token}, label=auth_token_name
                    )
                    secret.grant(relation)
                except ValueError as err:
                    logger.exception(
                        "Failed to add secret for relation %d", relation.id
                    )
                    raise JujuError(
                        f"Failed to create or grant secret for relation {relation.id}"
                    ) from err
                except ops.hookcmds.Error as err:
                    logger.exception(
                        "Failed to grant secret for relation %d", relation.id
                    )
                    raise JujuError(
                        f"Failed to grant secret for relation {relation.id}"
                    ) from err
                # The _base_url is set up by the parent class paas_charm.go.Charm.
                # It points to the ingress URL if there is one, otherwise it points to the K8S service.
                relation.data[self.app]["endpoint"] = self._base_url
                relation.data[self.app]["token"] = secret.id
            auth_token_set.discard(auth_token_name)

        # Clean up any auth tokens that are no longer needed
        for token_name in auth_token_set:
            try:
                secret = self.model.get_secret(label=token_name)
                secret.remove_all_revisions()
            except ops.SecretNotFoundError:
                # It is fine if the secret is already removed.
                logger.debug(
                    "Secret with label %s not found during cleanup", token_name
                )
            client.delete_auth_token(token_name)

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


if __name__ == "__main__":
    ops.main(GithubRunnerPlannerCharm)
