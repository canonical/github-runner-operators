#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import typing

import ops
import paas_charm.go
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

logger = logging.getLogger(__name__)


_REDELIVERY_FIELDS = (
    "github-path",
    "webhook-id",
    "github-app-id",
    "github-app-installation-id",
    "github-app-private-key",
)


class WebhookGatewayConfig(BaseModel):
    """Redelivery config validation model.

    Attrs:
        github_path: GitHub org or org/repo path for webhook redelivery.
        webhook_id: ID of the webhook to check deliveries for.
        github_app_id: GitHub App ID for authentication.
        github_app_installation_id: GitHub App installation ID.
        redelivery_interval: Interval in seconds between redelivery checks.
    """

    model_config = ConfigDict(extra="ignore")

    github_path: str | None = Field(alias="github-path", default=None)
    webhook_id: int | None = Field(alias="webhook-id", default=None, gt=0)
    github_app_id: int | None = Field(alias="github-app-id", default=None, gt=0)
    github_app_installation_id: int | None = Field(
        alias="github-app-installation-id", default=None, gt=0
    )
    redelivery_interval: int = Field(alias="redelivery-interval", default=600, gt=0)

    @model_validator(mode="before")
    @classmethod
    def validate_all_or_nothing(cls, data: dict[str, typing.Any]) -> dict[str, typing.Any]:
        """Validate that redelivery fields are all set or all unset."""
        present = [field for field in _REDELIVERY_FIELDS if data.get(field)]
        if not present:
            return data

        missing = [field for field in _REDELIVERY_FIELDS if not data.get(field)]
        if missing:
            raise ValueError(f"Incomplete redelivery config: missing {', '.join(missing)}")
        return data


class GithubRunnerWebhookGatewayCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)

    def is_ready(self) -> bool:
        """Validate redelivery config before deferring to base readiness checks.

        Returns:
            True if the charm is ready to start.
        """
        try:
            WebhookGatewayConfig.model_validate(dict(self.config))
        except ValidationError as exc:
            logger.error("Invalid redelivery config:\n%s", exc)
            self.update_app_and_unit_status(ops.BlockedStatus("Invalid redelivery config"))
            return False

        return super().is_ready()

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


if __name__ == "__main__":
    ops.main(GithubRunnerWebhookGatewayCharm)
