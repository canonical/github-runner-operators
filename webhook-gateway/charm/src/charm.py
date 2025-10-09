#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import typing

import ops
import paas_charm.go

logger = logging.getLogger(__name__)


class GithubRunnerWebhookGatewayCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)

    def _gen_environment(self) -> dict[str, str]:
        """Adding OpenTelemetry environment variables."""
        env = super()._gen_environment()
        env["OTEL_METRICS_EXPORTER"] = "prometheus"
        env["OTEL_EXPORTER_PROMETHEUS_HOST"] = "0.0.0.0"
        env["OTEL_EXPORTER_PROMETHEUS_PORT"] = str(self.config.get("metrics-port"))
        env["OTEL_LOGS_EXPORTER"] = "console"
        if env.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = env["OTEL_EXPORTER_OTLP_ENDPOINT"]
            del env["OTEL_EXPORTER_OTLP_ENDPOINT"]
            env["OTEL_TRACES_EXPORTER"] = "otlp"
            env["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] = "http/protobuf"
        return env


if __name__ == "__main__":
    ops.main(GithubRunnerWebhookGatewayCharm)
