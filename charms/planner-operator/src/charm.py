#!/usr/bin/env python3
# Copyright 2025 Ubuntu
# See LICENSE file for licensing details.

"""Go Charm entrypoint."""

import logging
import pathlib
import typing

import ops
import requests

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
            self.on.enable_flavor_action, self._on_enable_flavor_action
        )
        self.framework.observe(
            self.on.disable_flavor_action, self._on_disable_flavor_action
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

    def _on_enable_flavor_action(self, event: ops.ActionEvent) -> None:
        """Handle the enable-flavor action.

        Args:
            event: The action event.
        """
        flavor = event.params["flavor"]
        try:
            message = self._update_flavor_via_api(flavor, is_disabled=False)
            event.set_results({"message": message})
        except RuntimeError as e:
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
            message = self._update_flavor_via_api(flavor, is_disabled=True)
            event.set_results({"message": message})
        except RuntimeError as e:
            error_msg = str(e)
            event.fail(error_msg)
            logger.error("Failed to disable flavor %s: %s", flavor, error_msg)

    def _update_flavor_via_api(self, flavor_name: str, is_disabled: bool) -> str:
        """Update flavor via REST API.

        Args:
            flavor_name: The name of the flavor to update.
            is_disabled: Whether to disable (True) or enable (False) the flavor.

        Returns:
            Success message.

        Raises:
            RuntimeError: If admin token is not configured or API call fails.
        """
        env = self._gen_environment()
        port = env.get("APP_PORT", "8080")
        admin_token = env.get("APP_ADMIN_TOKEN_VALUE")

        if not admin_token:
            raise RuntimeError("Admin token not configured")

        url = f"http://127.0.0.1:{port}/api/v1/flavors/{flavor_name}"

        try:
            current_flavor = self._get_flavor(url, admin_token)
            if not current_flavor:
                raise RuntimeError(f"Flavor '{flavor_name}' not found")

            current_flavor["is_disabled"] = is_disabled

            response = requests.patch(
                url,
                json=current_flavor,
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=10,
            )
            response.raise_for_status()
            action = "disabled" if is_disabled else "enabled"
            return f"Flavor '{flavor_name}' {action} successfully"

        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else ""
            raise RuntimeError(
                f"HTTP error {e.response.status_code}: {error_body}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Connection error: {str(e)}") from e

    def _get_flavor(self, url: str, admin_token: str) -> dict[str, typing.Any] | None:
        """Get current flavor configuration from API.

        Args:
            url: The API URL for the flavor.
            admin_token: The admin authentication token.

        Returns:
            The flavor configuration dict, or None if not found.
        """
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            return None


if __name__ == "__main__":
    ops.main(GithubRunnerPlannerCharm)
