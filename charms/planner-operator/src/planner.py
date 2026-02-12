# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Planner API client."""

import dataclasses
import typing

import requests


@dataclasses.dataclass(frozen=True)
class Flavor:
    """Flavor as returned by the planner API."""

    name: str
    platform: str
    labels: list[str]
    priority: int
    minimum_pressure: int
    is_disabled: bool


class PlannerError(Exception):
    """Error for planner application issues."""


class PlannerClient:
    """Client for interacting with the planner API."""

    def __init__(self, base_url: str, admin_token: str, timeout: int = 10) -> None:
        """Initialize the planner client.

        Args:
            base_url: Base URL for the planner API.
            admin_token: Admin token for authentication.
            timeout: Request timeout in seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, typing.Any] | None = None,
    ) -> requests.Response:
        """Make an HTTP request to the planner API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API path (e.g., "/api/v1/flavors/small").
            json_data: Optional JSON payload.

        Returns:
            Response object.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._admin_token}"}

        try:
            response = requests.request(
                method=method,
                url=url,
                json=json_data,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            error_body = e.response.text if e.response else ""
            raise PlannerError(f"HTTP error {e.response.status_code}: {error_body}") from e
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Connection error: {str(e)}") from e

    def update_flavor(self, flavor_name: str, is_disabled: bool) -> None:
        """Update flavor disabled status.

        Args:
            flavor_name: The name of the flavor to update.
            is_disabled: Whether to disable (True) or enable (False) the flavor.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        self._request(
            method="PATCH",
            path=f"/api/v1/flavors/{flavor_name}",
            json_data={"is_disabled": is_disabled},
        )

    def get_flavor(self, flavor_name: str) -> Flavor | None:
        """Get a flavor by name.

        Args:
            flavor_name: The name of the flavor.

        Returns:
            The Flavor, or None if the flavor does not exist.

        Raises:
            PlannerError: If API returns non-2xx/404 status code.
            RuntimeError: If connection fails.
        """
        try:
            response = self._request(method="GET", path=f"/api/v1/flavors/{flavor_name}")
            data = response.json()
            return Flavor(
                name=data["name"],
                platform=data["platform"],
                labels=data["labels"],
                priority=data["priority"],
                minimum_pressure=data["minimum_pressure"],
                is_disabled=data["is_disabled"],
            )
        except PlannerError as err:
            if "HTTP error 404" in str(err):
                return None
            raise

    def create_flavor(
        self,
        flavor_name: str,
        platform: str,
        labels: list[str],
        priority: int,
        minimum_pressure: int,
        is_disabled: bool = False,
    ) -> None:
        """Create a flavor.

        Args:
            flavor_name: The name of the flavor.
            platform: Flavor platform (e.g. github).
            labels: Flavor labels.
            priority: Flavor priority.
            minimum_pressure: Flavor minimum pressure.
            is_disabled: Whether flavor starts disabled.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        try:
            self._request(
                method="POST",
                path=f"/api/v1/flavors/{flavor_name}",
                json_data={
                    "platform": platform,
                    "labels": labels,
                    "priority": priority,
                    "minimum_pressure": minimum_pressure,
                    "is_disabled": is_disabled,
                },
            )
        except PlannerError as err:
            if "HTTP error 409" in str(err):
                return
            raise

    def list_auth_token_names(self) -> list[str]:
        """List all auth token names.

        Returns:
            List of auth token names.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        response = self._request(method="GET", path="/api/v1/auth/token")
        return response.json()["names"]

    def create_auth_token(self, name: str) -> str:
        """Create an auth token.

        Args:
            name: The name of the auth token.

        Returns:
            The auth token value.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        response = self._request(method="POST", path=f"/api/v1/auth/token/{name}")
        return response.json()["token"]

    def delete_auth_token(self, name: str) -> None:
        """Delete an auth token.

        Args:
            name: The name of the auth token.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        self._request(method="DELETE", path=f"/api/v1/auth/token/{name}")

    def delete_flavor(self, flavor_name: str) -> None:
        """Delete a flavor.

        Args:
            flavor_name: The name of the flavor.

        Raises:
            PlannerError: If API returns non-2xx status code.
            RuntimeError: If connection fails.
        """
        self._request(method="DELETE", path=f"/api/v1/flavors/{flavor_name}")
