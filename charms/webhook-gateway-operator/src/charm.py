#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import typing

import ops
import paas_charm.go
from pydantic import Field, model_validator

logger = logging.getLogger(__name__)


class WebhookGatewayConfig(paas_charm.go.Charm.framework_config_class):
    """Framework config with redelivery validation.

    Attrs:
        github_path: GitHub org or org/repo path for webhook redelivery.
        webhook_id: ID of the webhook to check deliveries for.
        github_app_id: GitHub App ID for authentication.
        github_app_installation_id: GitHub App installation ID.
        redelivery_interval: Interval in seconds between redelivery checks.
    """

    github_path: str | None = Field(alias="github-path", default=None)
    webhook_id: int | None = Field(alias="webhook-id", default=None, gt=0)
    github_app_id: int | None = Field(alias="github-app-id", default=None, gt=0)
    github_app_installation_id: int | None = Field(
        alias="github-app-installation-id", default=None, gt=0
    )
    redelivery_interval: int = Field(alias="redelivery-interval", default=600, gt=0)

    @model_validator(mode="before")
    @classmethod
    def _validate_redelivery_all_or_nothing(cls, data: dict) -> dict:
        """Validate that redelivery fields are all set or all unset.

        Note: github-app-private-key is a secret-type config handled by paas_charm's
        user_defined_config path (not as a framework config field), so we check for
        it here in the raw input data.

        Args:
            data: raw input data.

        Returns:
            The unmodified input data.

        Raises:
            ValueError: if some redelivery fields are set but others are missing.
        """
        fields = (
            "github-path",
            "webhook-id",
            "github-app-id",
            "github-app-installation-id",
            "github-app-private-key",
        )
        present = [f for f in fields if data.get(f)]
        if not present:
            return data
        missing = [f for f in fields if not data.get(f)]
        if missing:
            raise ValueError(f"Incomplete redelivery config: missing {', '.join(missing)}")
        return data


class GithubRunnerWebhookGatewayCharm(paas_charm.go.Charm):
    """Go Charm service."""

    framework_config_class = WebhookGatewayConfig

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)

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
