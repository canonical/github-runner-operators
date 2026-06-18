# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Thin wrapper over the generated GARM API client for charm use."""

import logging
import time

import urllib3
import urllib3.exceptions

from garm_client.api.controller_info_api import ControllerInfoApi
from garm_client.api.credentials_api import CredentialsApi
from garm_client.api.first_run_api import FirstRunApi
from garm_client.api.login_api import LoginApi
from garm_client.api.organizations_api import OrganizationsApi
from garm_client.api.providers_api import ProvidersApi
from garm_client.api.repositories_api import RepositoriesApi
from garm_client.api.scalesets_api import ScalesetsApi
from garm_client.api_client import ApiClient
from garm_client.configuration import Configuration
from garm_client.exceptions import ApiException
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.forge_credentials import ForgeCredentials
from garm_client.models.new_user_params import NewUserParams
from garm_client.models.password_login_params import PasswordLoginParams
from garm_client.models.provider import Provider
from garm_client.models.scale_set import ScaleSet
from garm_client.models.update_scale_set_params import UpdateScaleSetParams

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30
_READINESS_POLL_INTERVAL = 1  # seconds between retries
_READINESS_TIMEOUT = 30  # seconds before giving up


class GarmApiError(Exception):
    """Raised when a GARM API call fails unexpectedly."""


class GarmConnectionError(GarmApiError):
    """Raised when a network-level connection to GARM fails (port closed, refused)."""


class GarmEntityNotFoundError(GarmApiError):
    """Raised when a required GARM entity (org/repo/provider) cannot be found."""


class GarmApiClient:
    """HTTP client for the GARM REST API.

    Covers unauthenticated endpoints (initialisation check, first-run) and login.
    Use ``GarmAuthenticatedClient`` for authenticated operations.
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
        """Log in to the GARM API and return a JWT token.

        Args:
            username: Admin username.
            password: Admin password.

        Raises:
            GarmApiError: If login fails or response has no token.

        Returns:
            JWT token string.
        """
        with self._api_client() as client:
            api = LoginApi(api_client=client)
            try:
                result = api.login(
                    body=PasswordLoginParams(username=username, password=password),
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(f"GARM login failed ({exc.status}): {exc.body}") from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
        if not result.token:
            raise GarmApiError("login response did not contain a token")
        return result.token


class GarmAuthenticatedClient:
    """Authenticated GARM API client for scaleset and entity management operations."""

    def __init__(self, base_url: str, token: str) -> None:
        """Create an authenticated client.

        Args:
            base_url: Full base URL including the API prefix,
                e.g. ``http://127.0.0.1:9997/api/v1``.
            token: JWT Bearer token from ``GarmApiClient.login()``.
        """
        self._base_url = base_url
        self._token = token

    def _api_client(self) -> ApiClient:
        """Build an authenticated ApiClient with JWT Bearer token."""
        return ApiClient(
            configuration=Configuration(host=self._base_url),
            header_name="Authorization",
            header_value=f"Bearer {self._token}",
        )

    def list_providers(self) -> list[Provider]:
        """List all registered GARM providers.

        Returns:
            List of Provider model objects.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                return (
                    ProvidersApi(api_client=client).list_providers(
                        _request_timeout=_REQUEST_TIMEOUT
                    )
                    or []
                )
            except ApiException as exc:
                raise GarmApiError(f"Failed to list providers ({exc.status}): {exc.body}") from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def list_credentials(self) -> list[ForgeCredentials]:
        """List all registered GARM credentials.

        Returns:
            List of ForgeCredentials model objects.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                return (
                    CredentialsApi(api_client=client).list_credentials(
                        _request_timeout=_REQUEST_TIMEOUT
                    )
                    or []
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to list credentials ({exc.status}): {exc.body}"
                ) from exc

    def list_scalesets(self) -> list[ScaleSet]:
        """List all scalesets across all entities.

        Returns:
            List of ScaleSet model objects.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                return (
                    ScalesetsApi(api_client=client).list_scalesets(
                        _request_timeout=_REQUEST_TIMEOUT
                    )
                    or []
                )
            except ApiException as exc:
                raise GarmApiError(f"Failed to list scalesets ({exc.status}): {exc.body}") from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def find_org_id(self, org_name: str) -> str | None:
        """Find a GARM organization's UUID by name.

        Args:
            org_name: GitHub organization name registered in GARM.

        Returns:
            Organization UUID string, or None if not found.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                orgs = (
                    OrganizationsApi(api_client=client).list_orgs(
                        name=org_name,
                        _request_timeout=_REQUEST_TIMEOUT,
                    )
                    or []
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to list organizations ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
        for org in orgs:
            if org.name == org_name:
                return org.id
        return None

    def find_repo_id(self, repo_name: str) -> str | None:
        """Find a GARM repository's UUID by name.

        Args:
            repo_name: Repository name (owner/repo format) registered in GARM.

        Returns:
            Repository UUID string, or None if not found.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                # The GARM repos API does not support a server-side name filter
                # (unlike orgs which accepts name=), so we fetch all and filter client-side.
                repos = (
                    RepositoriesApi(api_client=client).list_repos(
                        _request_timeout=_REQUEST_TIMEOUT,
                    )
                    or []
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to list repositories ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
        for repo in repos:
            if repo.name == repo_name:
                return repo.id
        return None

    def create_org_scaleset(self, org_id: str, params: CreateScaleSetParams) -> ScaleSet:
        """Create a scaleset under a GARM organization.

        Args:
            org_id: GARM organization UUID.
            params: Scaleset creation parameters.

        Returns:
            Created ScaleSet model object.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                return OrganizationsApi(api_client=client).create_org_scale_set(
                    org_id=org_id,
                    body=params,
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to create org scaleset ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def create_repo_scaleset(self, repo_id: str, params: CreateScaleSetParams) -> ScaleSet:
        """Create a scaleset under a GARM repository.

        Args:
            repo_id: GARM repository UUID.
            params: Scaleset creation parameters.

        Returns:
            Created ScaleSet model object.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                return RepositoriesApi(api_client=client).create_repo_scale_set(
                    repo_id=repo_id,
                    body=params,
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to create repo scaleset ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def update_scaleset(self, scaleset_id: int, params: UpdateScaleSetParams) -> ScaleSet:
        """Update an existing scaleset.

        Args:
            scaleset_id: Integer scaleset ID.
            params: Fields to update.

        Returns:
            Updated ScaleSet model object.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                return ScalesetsApi(api_client=client).update_scale_set(
                    scaleset_id=str(scaleset_id),
                    body=params,
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to update scaleset {scaleset_id} ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc

    def delete_scaleset(self, scaleset_id: int) -> None:
        """Delete a scaleset.

        Args:
            scaleset_id: Integer scaleset ID.

        Raises:
            GarmApiError: On API error.
        """
        with self._api_client() as client:
            try:
                ScalesetsApi(api_client=client).delete_scale_set(
                    scaleset_id=str(scaleset_id),
                    _request_timeout=_REQUEST_TIMEOUT,
                )
            except ApiException as exc:
                raise GarmApiError(
                    f"Failed to delete scaleset {scaleset_id} ({exc.status}): {exc.body}"
                ) from exc
            except urllib3.exceptions.HTTPError as exc:
                raise GarmConnectionError(f"GARM connection error: {exc}") from exc
