#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import re
import typing

import ops
from ops import BlockedStatus

import paas_charm.go

ADMIN_TOKEN_PATTERN = re.compile(r"^planner_v0_[A-Za-z0-9_-]{20}$")

logger = logging.getLogger(__name__)


class GithubRunnerPlannerCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)

    def is_ready(self) -> bool:
        """Check if the charm is ready to start the workload application."""
        secret_id = self.config.get("admin-token")
        if secret_id:
            try:
                secret = self.model.get_secret(id=secret_id)
                content = secret.get_content()
                token_value = content.get("value", "")
                if not ADMIN_TOKEN_PATTERN.match(token_value):
                    self.unit.status = BlockedStatus(
                        "invalid admin-token format; expected 'planner_v0_' + 20 chars [A-Za-z0-9_-]"
                    )
                    return False
            except Exception as e:
                logger.warning("Failed to read admin-token secret: %s", e)
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
    ops.main(GithubRunnerPlannerCharm)
