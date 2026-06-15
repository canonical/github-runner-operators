# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Thin wrapper over the generated GARM API client for charm use."""

import logging

import urllib3.exceptions

from garm_client.api.controller_info_api import ControllerInfoApi
from garm_client.api.first_run_api import FirstRunApi
from garm_client.api_client import ApiClient
from garm_client.configuration import Configuration
from garm_client.exceptions import ApiException
from garm_client.models.new_user_params import NewUserParams

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 30


class GarmApiError(Exception):
    """Raised when a GARM API call fails unexpectedly."""


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
                raise GarmApiError(f"GARM connection error: {exc}") from exc

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
                raise GarmApiError(f"GARM connection error: {exc}") from exc
        logger.info("GARM first-run initialisation complete for user '%s'", username)
