#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import typing

import ops
import paas_charm.go

logger = logging.getLogger(__name__)


_REDELIVERY_REQUIRED_FIELDS = (
    "github-path",
    "webhook-id",
    "github-app-id",
    "github-app-installation-id",
    "github-app-private-key",
)
_REDELIVERY_INT_FIELDS = (
    "webhook-id",
    "github-app-id",
    "github-app-installation-id",
    "redelivery-interval",
)


class GithubRunnerWebhookGatewayCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)

    def is_ready(self) -> bool:
        """Check if the charm is ready to start the workload application.

        Returns:
            True if the charm is ready to start the workload application.
        """
        error = self._validate_redelivery_config()
        if error:
            logger.error("Invalid redelivery config: %s", error)
            self.update_app_and_unit_status(ops.BlockedStatus("Invalid redelivery config"))
            return False
        return super().is_ready()

    def _validate_redelivery_config(self) -> str | None:
        """Validate redelivery-related config options.

        Returns:
            An error message if validation fails, None otherwise.
        """
        present = [f for f in _REDELIVERY_REQUIRED_FIELDS if self.config.get(f)]
        if not present:
            return None

        missing = [f for f in _REDELIVERY_REQUIRED_FIELDS if not self.config.get(f)]
        if missing:
            return f"Incomplete redelivery config: missing {', '.join(missing)}"

        invalid = [
            f
            for f in _REDELIVERY_INT_FIELDS
            if (val := self.config.get(f)) is not None and (not isinstance(val, int) or val <= 0)
        ]
        if invalid:
            return f"Invalid config (must be positive integers): {', '.join(invalid)}"

        return None

    def _create_app(self):
        """Patch _create_app to add OpenTelemetry and redelivery environment variables."""
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

            if charm.config.get("github-path"):
                github_path = str(charm.config["github-path"])
                parts = github_path.split("/", 1)
                env["APP_WEBHOOK_GITHUB_ORG"] = parts[0]
                if len(parts) > 1:
                    env["APP_WEBHOOK_GITHUB_REPO"] = parts[1]
            if charm.config.get("webhook-id"):
                env["APP_WEBHOOK_ID"] = str(charm.config["webhook-id"])
            if charm.config.get("redelivery-interval"):
                env["APP_REDELIVERY_INTERVAL_SECONDS"] = str(charm.config["redelivery-interval"])
            if charm.config.get("github-app-id"):
                env["APP_GITHUB_APP_ID"] = str(charm.config["github-app-id"])
            if charm.config.get("github-app-installation-id"):
                env["APP_GITHUB_APP_INSTALLATION_ID"] = str(
                    charm.config["github-app-installation-id"]
                )

            return env

        app = super()._create_app()
        setattr(app, "gen_environment", gen_environment)
        return app


if __name__ == "__main__":
    ops.main(GithubRunnerWebhookGatewayCharm)
