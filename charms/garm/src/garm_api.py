#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM REST API client."""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class GarmApiError(Exception):
    """Raised when the GARM REST API returns an unexpected response."""


class GarmClient:
    """Thin HTTP client for the GARM REST API."""

    def __init__(self, base_url: str) -> None:
        """Initialise the client.

        Args:
            base_url: GARM API base URL, e.g. 'http://localhost:9997/api/v1'.
        """
        self.base_url = base_url.rstrip("/")
        self.token: str = ""

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        auth: bool = True,
    ) -> Any:
        """Make an HTTP request to the GARM API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: Path relative to base_url (must start with /).
            payload: Optional JSON request body.
            auth: Whether to include the Bearer token header.

        Raises:
            GarmApiError: If the response status is not 2xx or a network error occurs.

        Returns:
            Parsed JSON response body, or None for empty responses.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                if not body:
                    return None
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            raise GarmApiError(
                f"{method} {url} failed with status {exc.code}: {exc.read().decode()[:200]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GarmApiError(f"{method} {url} failed: {exc.reason}") from exc

    def first_run(
        self,
        username: str,
        password: str,
        email: str,
        full_name: str,
    ) -> None:
        """Complete GARM first-run initialisation (idempotent — HTTP 409 is silently ignored).

        Args:
            username: Admin username.
            password: Admin password.
            email: Admin email address.
            full_name: Admin display name.

        Raises:
            GarmApiError: On unexpected API errors (not 409).
        """
        try:
            self._request(
                "POST",
                "/first-run",
                {
                    "username": username,
                    "password": password,
                    "email": email,
                    "full_name": full_name,
                },
                auth=False,
            )
        except GarmApiError as exc:
            if "status 409" in str(exc):
                logger.debug("GARM first-run already completed (409)")
                return
            raise

    def configure_controller(
        self,
        metadata_url: str,
        callback_url: str,
        webhook_url: str,
    ) -> None:
        """Configure GARM controller URLs (idempotent).

        Args:
            metadata_url: URL for runner metadata endpoint.
            callback_url: URL for runner callback endpoint.
            webhook_url: URL for GitHub webhooks endpoint.

        Raises:
            GarmApiError: On API error.
        """
        self._request(
            "PUT",
            "/controller",
            {
                "metadata_url": metadata_url,
                "callback_url": callback_url,
                "webhook_url": webhook_url,
            },
        )

    def login(self, username: str, password: str) -> str:
        """Log in to the GARM API and return a JWT token.

        Args:
            username: Admin username.
            password: Admin password.

        Raises:
            GarmApiError: If login fails or response has no token.

        Returns:
            JWT token string.
        """
        result = self._request(
            "POST",
            "/auth/login",
            {"username": username, "password": password},
            auth=False,
        )
        token = (result or {}).get("token", "")
        if not token:
            raise GarmApiError("login response did not contain a token")
        return token

    def list_providers(self) -> list[dict[str, Any]]:
        """List all registered GARM providers.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of provider dicts (each has at minimum a 'name' key).
        """
        return self._request("GET", "/providers") or []

    def list_credentials(self) -> list[dict[str, Any]]:
        """List all registered GARM credentials.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of credential dicts (each has at minimum a 'name' key).
        """
        return self._request("GET", "/credentials") or []

    def list_scalesets(self) -> list[dict[str, Any]]:
        """List all scalesets.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of scaleset dicts (each has at minimum 'id' and 'name' keys).
        """
        return self._request("GET", "/scalesets") or []

    def create_scaleset(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new scaleset.

        Args:
            payload: CreateScaleSetParams dict.

        Raises:
            GarmApiError: On API error.

        Returns:
            Created scaleset dict.
        """
        return self._request("POST", "/scalesets", payload)

    def update_scaleset(self, scaleset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing scaleset.

        Args:
            scaleset_id: Scaleset UUID.
            payload: UpdateScaleSetParams dict (only changed fields needed).

        Raises:
            GarmApiError: On API error.

        Returns:
            Updated scaleset dict.
        """
        return self._request("PUT", f"/scalesets/{scaleset_id}", payload)

    def delete_scaleset(self, scaleset_id: str) -> None:
        """Delete a scaleset.

        Args:
            scaleset_id: Scaleset UUID.

        Raises:
            GarmApiError: On API error.
        """
        self._request("DELETE", f"/scalesets/{scaleset_id}")

    def list_templates(
        self,
        os_type: str | None = None,
        forge_type: str | None = None,
        partial_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List runner templates, optionally filtered by type or name.

        Args:
            os_type: Optional OS type filter (e.g. "linux", "windows").
            forge_type: Optional forge type filter (e.g. "github", "gitea").
            partial_name: Optional substring to filter template names.

        Raises:
            GarmApiError: On API error.

        Returns:
            List of template dicts, each containing at minimum 'id' and 'name'.
        """
        params = {
            k: v
            for k, v in {
                "os_type": os_type,
                "forge_type": forge_type,
                "partial_name": partial_name,
            }.items()
            if v is not None
        }
        path = "/templates"
        if params:
            path = f"{path}?{urllib.parse.urlencode(params)}"
        return self._request("GET", path) or []

    def get_template(self, template_id: int) -> dict[str, Any]:
        """Fetch a single template by ID.

        Args:
            template_id: Numeric template ID.

        Raises:
            GarmApiError: On API error.

        Returns:
            Template dict with at minimum 'id', 'name', 'os_type', 'forge_type', and 'data'.
        """
        return self._request("GET", f"/templates/{template_id}")

    def create_template(
        self,
        *,
        name: str,
        data: bytes,
        os_type: str = "linux",
        forge_type: str = "github",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new runner template.

        The ``data`` bytes are base64-encoded before sending because GARM stores
        template scripts as a Go ``[]byte``, which serialises to base64 in JSON.

        Args:
            name: Template name.
            data: Raw script bytes to store in the template.
            os_type: OS type (default: "linux").
            forge_type: Forge type (default: "github").
            description: Optional human-readable description.

        Raises:
            GarmApiError: On API error.

        Returns:
            Created template dict.
        """
        payload = {
            "name": name,
            "data": base64.b64encode(data).decode(),
            "os_type": os_type,
            "forge_type": forge_type,
            "description": description,
        }
        return self._request("POST", "/templates", payload)

    def update_template(
        self,
        template_id: int,
        *,
        data: bytes,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing template's data and optionally its name or description.

        Only ``data`` is always sent; ``name`` and ``description`` are included
        only when explicitly provided, leaving unspecified fields unchanged on
        the server.

        Args:
            template_id: Numeric template ID.
            data: New raw script bytes (required by the GARM API).
            name: New template name, or None to leave unchanged.
            description: New description, or None to leave unchanged.

        Raises:
            GarmApiError: On API error.

        Returns:
            Updated template dict.
        """
        payload: dict[str, Any] = {"data": base64.b64encode(data).decode()}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        return self._request("PUT", f"/templates/{template_id}", payload)

    def delete_template(self, template_id: int) -> None:
        """Delete a template by ID.

        Args:
            template_id: Numeric template ID.

        Raises:
            GarmApiError: On API error.
        """
        self._request("DELETE", f"/templates/{template_id}")
