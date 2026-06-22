# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Thin wrapper over the generated GARM API client for charm use."""

import logging
import time

import urllib3
import urllib3.exceptions

from garm_client.api.controller_info_api import ControllerInfoApi
from garm_client.api.first_run_api import FirstRunApi
from garm_client.api.login_api import LoginApi
from garm_client.api.templates_api import TemplatesApi
from garm_client.api_client import ApiClient
from garm_client.configuration import Configuration
from garm_client.exceptions import ApiException
from garm_client.models.create_template_params import CreateTemplateParams
from garm_client.models.new_user_params import NewUserParams
from garm_client.models.password_login_params import PasswordLoginParams
from garm_client.models.template import Template

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30
_READINESS_POLL_INTERVAL = 1  # seconds between retries
_READINESS_TIMEOUT = 30  # seconds before giving up


class GarmApiError(Exception):
    """Raised when a GARM API call fails unexpectedly."""


class GarmConnectionError(GarmApiError):
    """Raised when a network-level connection to GARM fails (port closed, refused)."""


class GarmApiClient:
    """HTTP client for the GARM REST API.

    Covers the two unauthenticated endpoints the charm needs: initialisation
    check and first-run admin user creation.
    """

    def __init__(self, base_url: str) -> None:
        """Create a client bound to the given GARM base URL.

        Args:
            base_url: Full base URL including the API prefix,
                e.g. ``http://127.0.0.1:9997/api/v1``.
        """
        self._base_url = base_url

    def _api_client(self) -> ApiClient:
        """Build an unauthenticated ApiClient."""
        return ApiClient(configuration=Configuration(host=self._base_url))

    def is_initialized(self) -> bool:
        """Return True if GARM has already been initialised (first-run done).

        GARM returns 409 Conflict on ``GET /controller-info`` until the initial
        admin user has been created via ``POST /first-run``.

        Returns:
            True if GARM is initialised, False if it is waiting for first-run.

        Raises:
            GarmApiError: If the API returns an unexpected error.
        """
        with self._api_client() as client:
            api = ControllerInfoApi(api_client=client)
            try:
                api.controller_info(_request_timeout=_REQUEST_TIMEOUT)
                return True
            except ApiException as exc:
                if exc.status == 409:
                    return False
                raise GarmApiError(
                    f"Unexpected response from GARM controller-info ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def wait_for_ready(self, timeout: float = _READINESS_TIMEOUT) -> None:
        """Wait until the GARM HTTP API is accepting connections.

        Polls is_initialized(): both True (200) and False (409) indicate the HTTP
        server is up. Only retries on GarmConnectionError (network-level failures);
        unexpected HTTP errors propagate immediately.

        `is_initialized` is used due to it not requiring auth, and there is no dedicated,
        readiness/health check API.

        Args:
            timeout: Maximum seconds to wait before raising.

        Raises:
            GarmConnectionError: If GARM does not respond within *timeout* seconds.
            GarmApiError: If GARM responds with an unexpected HTTP status.
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.is_initialized()
                return
            except GarmConnectionError:
                if time.monotonic() >= deadline:
                    raise GarmConnectionError(f"GARM did not become ready within {timeout:.0f}s")
                time.sleep(_READINESS_POLL_INTERVAL)

    def first_run(
        self,
        username: str,
        password: str,
        email: str,
        full_name: str,
    ) -> None:
        """Create the initial admin user (GARM first-run initialisation).

        Args:
            username: Admin username to create.
            password: Admin password (must satisfy GARM's strong-password policy:
                min 12 chars, uppercase, lowercase, digit, symbol).
            email: Admin e-mail address.
            full_name: Admin full name.

        Raises:
            GarmApiError: If the first-run call fails.
        """
        with self._api_client() as client:
            api = FirstRunApi(api_client=client)
            try:
                api.first_run(
                    body=NewUserParams(
                        username=username,
                        password=password,
                        email=email,
                        full_name=full_name,
                    ),
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(f"GARM first-run failed ({exc.status}): {exc.body}") from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
        logger.info("GARM first-run initialisation complete for user '%s'", username)

    def login(self, username: str, password: str) -> str:
        """Authenticate with GARM and return a JWT token.

        Args:
            username: GARM admin username.
            password: GARM admin password.

        Returns:
            JWT token string.

        Raises:
            GarmApiError: If login fails.
        """
        with self._api_client() as client:
            api = LoginApi(api_client=client)
            try:
                response = api.login(
                    body=PasswordLoginParams(username=username, password=password),
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(f"GARM login failed ({exc.status}): {exc.body}") from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
        if not response.token:
            raise GarmApiError("GARM login returned empty token")
        return response.token

    def _authenticated_api_client(self, token: str) -> ApiClient:
        """Build an ApiClient configured with a Bearer token.

        Args:
            token: JWT token returned from login().

        Returns:
            Configured ApiClient with Bearer auth header.
        """
        config = Configuration(
            host=self._base_url,
            api_key={"Bearer": token},
            api_key_prefix={"Bearer": "Bearer"},
        )
        return ApiClient(configuration=config)

    def list_templates(self, token: str) -> list[Template]:
        """List all runner install templates known to GARM.

        Args:
            token: JWT token from login().

        Returns:
            List of Template objects.

        Raises:
            GarmApiError: If the API call fails.
        """
        with self._authenticated_api_client(token) as client:
            api = TemplatesApi(api_client=client)
            try:
                return api.list_templates(_request_timeout=_REQUEST_TIMEOUT) or []
            except ApiException as exc:
                raise GarmApiError(
                    f"GARM list_templates failed ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def get_template(self, token: str, template_id: int) -> Template:
        """Fetch a single runner install template by ID.

        Args:
            token: JWT token from login().
            template_id: Numeric template ID.

        Returns:
            The requested Template.

        Raises:
            GarmApiError: If the API call fails.
        """
        with self._authenticated_api_client(token) as client:
            api = TemplatesApi(api_client=client)
            try:
                return api.get_template(
                    template_id=template_id, _request_timeout=_REQUEST_TIMEOUT
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"GARM get_template({template_id}) failed ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def create_template(
        self,
        token: str,
        name: str,
        description: str,
        forge_type: str,
        os_type: str,
        data: bytes,
    ) -> Template:
        """Create a new runner install template.

        Args:
            token: JWT token from login().
            name: Template name.
            description: Human-readable description.
            forge_type: Source forge type, e.g. ``"github"``.
            os_type: OS type, e.g. ``"linux"``.
            data: Raw shell script bytes for the template body.

        Returns:
            The created Template.

        Raises:
            GarmApiError: If the API call fails.
        """
        with self._authenticated_api_client(token) as client:
            api = TemplatesApi(api_client=client)
            try:
                return api.create_template(
                    body=CreateTemplateParams(
                        name=name,
                        description=description,
                        forge_type=forge_type,
                        os_type=os_type,
                        data=list(data),
                    ),
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"GARM create_template failed ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def delete_template(self, token: str, template_id: int) -> None:
        """Delete a runner install template by ID.

        Args:
            token: JWT token from login().
            template_id: Numeric template ID to delete.

        Raises:
            GarmApiError: If the API call fails.
        """
        with self._authenticated_api_client(token) as client:
            api = TemplatesApi(api_client=client)
            try:
                api.delete_template(
                    template_id=template_id, _request_timeout=_REQUEST_TIMEOUT
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"GARM delete_template({template_id}) failed ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
