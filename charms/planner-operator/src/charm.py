#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import pathlib
import typing

import requests
import ops

import paas_charm.go

logger = logging.getLogger(__name__)


HTTP_PORT: typing.Final[int] = 8080
PLANNER_RELATION_NAME: typing.Final[str] = "planner"
ADMIN_TOKEN_CONFIG_NAME: typing.Final[str] = "admin-token"


class ConfigError(Exception):
    """Error for configuration issues."""


class PlannerError(Exception):
    """Error for planner application issues."""


class GithubRunnerPlannerCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)

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

    def _on_manager_relation_changed(self, _: ops.RelationChangedEvent) -> None:
        """Handle changes to the github-runner-manager relation."""
        self._setup()

    def _setup(self) -> None:
        """Setup the planner application."""
        self.unit.status = ops.MaintenanceStatus("Setting up planner application")
        try:
            admin_token = self._get_admin_token()
        except ConfigError:
            logger.exception("Missing %s configuration", ADMIN_TOKEN_CONFIG_NAME)
            self.unit.status = ops.BlockedStatus(
                f"Missing {ADMIN_TOKEN_CONFIG_NAME} configuration"
            )
            return

        self.unit.status = ops.MaintenanceStatus("Setup planner integrations")
        self._setup_planner_relation(admin_token)
        self.unit.status = ops.ActiveStatus()

    def _setup_planner_relation(self, admin_token: str) -> None:
        """Setup the planner relations if this unit is the leader.

        Args:
            admin_token: The admin token for making API requests to planner.
        """
        if not self.unit.is_leader():
            return

        auth_token_names = None
        try:
            response = requests.get(
                f"http://localhost:{HTTP_PORT}/api/v1/auth/token",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            response.raise_for_status()
            auth_token_names = response.json()["name"]
        except requests.RequestException as err:
            logger.exception("Failed to list the names of auth tokens")
            raise PlannerError("Failed to list the names of auth tokens") from err

        if auth_token_names is None:
            auth_token_names = []
        auth_token_set = set(auth_token_names)

        relations = self.model.relations[PLANNER_RELATION_NAME]
        if not relations or not (relation := relations[0]).units:
            return

        auth_token_name = self._get_auth_token_name(relation.id)
        if auth_token_name not in auth_token_set:
            auth_token = self._create_auth_token(admin_token, auth_token_name)
            secret = self.app.add_secret({"token": auth_token}, label=auth_token_name)
            secret.grant(relation)
            relation.data[self.app][
                "endpoint"
            ] = f"http://{self.model.get_binding(relation).network.bind_address}:{HTTP_PORT}"
            relation.data[self.app]["token"] = secret.id
        auth_token_set.discard(auth_token_name)

        # Clean up any auth tokens that are no longer needed
        for token_name in auth_token_set:
            self.model.get_secret(label=token_name).remove_all_revisions()
            self._remove_auth_token(admin_token, token_name)

    @staticmethod
    def _create_auth_token(admin_token: str, name: str) -> str:
        """Create an auth token secret in the planner application.

        Args:
            admin_token: The admin token for making API requests to planner.
            name: The name of the auth token.

        Returns:
            The auth token.
        """
        try:
            response = requests.post(
                f"http://localhost:{HTTP_PORT}/api/v1/auth/token/{name}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            response.raise_for_status()
            return response.json()["token"]
        except requests.RequestException as err:
            logger.exception("Failed to create auth token %s", name)
            raise PlannerError(f"Failed to create auth token {name}") from err

    @staticmethod
    def _remove_auth_token(admin_token: str, name: str) -> None:
        """Remove an auth token secret in the planner application.

        Args:
            admin_token: The admin token for making API requests to planner.
            name: The name of the auth token.
        """
        try:
            response = requests.delete(
                f"http://localhost:{HTTP_PORT}/api/v1/auth/token/{name}",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            response.raise_for_status()
        except requests.RequestException as err:
            logger.exception("Failed to remove auth token %s", name)
            raise PlannerError(f"Failed to remove auth token {name}") from err

    def _get_admin_token(self) -> str:
        admin_token_secret_id = self.config.get(ADMIN_TOKEN_CONFIG_NAME)
        if not admin_token_secret_id:
            raise ConfigError(f"{ADMIN_TOKEN_CONFIG_NAME} config value is not set")
        admin_token_secret = self.model.get_secret(id=admin_token_secret_id)
        return admin_token_secret.get_content().get("value")

    @staticmethod
    def _get_auth_token_name(relation_id: int) -> str:
        """Build the auth token name based on relation ID.

        Args:
            relation_id: The relation ID.

        Returns:
            The auth token name.
        """
        return f"relation-{relation_id}"


if __name__ == "__main__":
    ops.main(GithubRunnerPlannerCharm)
