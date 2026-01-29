#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import pathlib
import typing

import ops

import paas_charm.go

logger = logging.getLogger(__name__)


class GithubRunnerPlannerCharm(paas_charm.go.Charm):
    """Go Charm service."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(
            self.on.update_flavor_action, self._on_update_flavor_action
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

    def _on_update_flavor_action(self, event: ops.ActionEvent) -> None:
        """Handle the update-flavor action.

        Args:
            event: The action event.
        """
        flavor = event.params["flavor"]
        disable = event.params["disable"]

        try:
            process = self._container.exec(
                [
                    "/usr/local/bin/planner",
                    "update-flavor",
                    "--flavor",
                    flavor,
                    "--disable" if disable else "--enable",
                ],
                environment=self._gen_environment(),
                timeout=30,
                combine_stderr=True,
            )
            stdout, _ = process.wait_output()
            event.set_results(
                {
                    "message": f"Flavor '{flavor}' {'disabled' if disable else 'enabled'} successfully",
                    "output": stdout,
                }
            )
        except ops.pebble.ExecError as e:
            event.fail(f"Failed to update flavor: {e.stdout}")
            logger.error("Failed to update flavor %s: %s", flavor, e.stdout)
        except ops.pebble.TimeoutError:
            event.fail("Command timed out")
            logger.error("Update flavor command timed out for %s", flavor)
        except Exception as e:
            event.fail(f"Unexpected error: {str(e)}")
            logger.exception("Unexpected error updating flavor %s", flavor)


if __name__ == "__main__":
    ops.main(GithubRunnerPlannerCharm)
