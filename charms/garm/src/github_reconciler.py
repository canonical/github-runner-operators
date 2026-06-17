#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GitHub reconciler: diffs desired vs observed GARM GitHub endpoints and credentials."""

import logging
from dataclasses import dataclass, field

from garm_api import GarmAuthenticatedClient
from garm_client.models.create_github_credentials_params import CreateGithubCredentialsParams
from garm_client.models.create_github_endpoint_params import CreateGithubEndpointParams
from garm_client.models.github_app import GithubApp
from garm_client.models.update_github_credentials_params import UpdateGithubCredentialsParams
from garm_client.models.update_github_endpoint_params import UpdateGithubEndpointParams

logger = logging.getLogger(__name__)

# The built-in GARM GitHub endpoint that must never be deleted.
DEFAULT_GITHUB_ENDPOINT = "github.com"


@dataclass
class EndpointSpec:
    """Desired state for one GARM GitHub endpoint."""

    name: str
    base_url: str = ""
    api_base_url: str = ""
    upload_base_url: str = ""
    description: str = ""


@dataclass
class CredentialSpec:
    """Desired state for one GARM GitHub credential."""

    name: str
    endpoint: str
    app_id: int
    installation_id: int
    private_key_bytes: list[int] = field(default_factory=list)
    description: str = ""


class GithubReconciler:
    """Reconciles GARM GitHub endpoints and credentials against desired spec lists."""

    def __init__(self, client: GarmAuthenticatedClient) -> None:
        """Initialise the reconciler.

        Args:
            client: Authenticated GarmAuthenticatedClient instance.
        """
        self._client = client

    def reconcile(self, endpoints: list[EndpointSpec], credentials: list[CredentialSpec]) -> None:
        """Sync GARM GitHub endpoints and credentials to match the desired state.

        Endpoints are reconciled first because credentials reference them.
        Performs the minimum set of CREATE / UPDATE / DELETE operations.

        Args:
            endpoints: The full desired set of GitHub endpoints.
            credentials: The full desired set of GitHub credentials.
        """
        self._reconcile_endpoints(endpoints)
        self._reconcile_credentials(credentials)

    def _reconcile_endpoints(self, desired: list[EndpointSpec]) -> None:
        # The charm creates/updates the endpoints it is asked to manage but never deletes
        # endpoints it did not create: doing so would remove the built-in github.com endpoint
        # or any enterprise endpoints an operator configured out of band. Endpoint deletion
        # belongs with explicit custom-endpoint management, which is not in scope here.
        observed = {e.name: e for e in self._client.list_github_endpoints()}
        for spec in desired:
            if spec.name in observed:
                self._maybe_update_endpoint(observed[spec.name], spec)
            else:
                self._create_endpoint(spec)

    def _create_endpoint(self, spec: EndpointSpec) -> None:
        kwargs: dict = {"name": spec.name}
        if spec.base_url:
            kwargs["base_url"] = spec.base_url
        if spec.api_base_url:
            kwargs["api_base_url"] = spec.api_base_url
        if spec.upload_base_url:
            kwargs["upload_base_url"] = spec.upload_base_url
        if spec.description:
            kwargs["description"] = spec.description
        params = CreateGithubEndpointParams(**kwargs)
        logger.info("Creating GitHub endpoint '%s'", spec.name)
        self._client.create_github_endpoint(params)

    def _maybe_update_endpoint(self, observed, spec: EndpointSpec) -> None:
        if not self._endpoint_needs_update(observed, spec):
            logger.debug("GitHub endpoint '%s' is up to date", spec.name)
            return
        params = UpdateGithubEndpointParams(
            base_url=spec.base_url or None,
            api_base_url=spec.api_base_url or None,
            upload_base_url=spec.upload_base_url or None,
            description=spec.description or None,
        )
        logger.info("Updating GitHub endpoint '%s'", spec.name)
        self._client.update_github_endpoint(spec.name, params)

    @staticmethod
    def _endpoint_needs_update(observed, spec: EndpointSpec) -> bool:
        return (
            observed.base_url != (spec.base_url or None)
            or observed.api_base_url != (spec.api_base_url or None)
            or observed.upload_base_url != (spec.upload_base_url or None)
            or observed.description != (spec.description or None)
        )

    def _reconcile_credentials(self, desired: list[CredentialSpec]) -> None:
        observed = {c.name: c for c in self._client.list_credentials()}
        desired_names = {spec.name for spec in desired}

        for spec in desired:
            if spec.name in observed:
                self._maybe_update_credential(observed[spec.name], spec)
            else:
                self._create_credential(spec)

        for name, cred in observed.items():
            if name not in desired_names and cred.id is not None:
                logger.info("Deleting orphaned GitHub credential '%s' (id=%s)", name, cred.id)
                self._client.delete_credentials(cred.id)

    def _create_credential(self, spec: CredentialSpec) -> None:
        params = CreateGithubCredentialsParams(
            name=spec.name,
            endpoint=spec.endpoint,
            auth_type="app",
            description=spec.description or None,
            app=GithubApp(
                app_id=spec.app_id,
                installation_id=spec.installation_id,
                private_key_bytes=spec.private_key_bytes,
            ),
        )
        logger.info("Creating GitHub credential '%s'", spec.name)
        self._client.create_credentials(params)

    def _maybe_update_credential(self, observed, spec: CredentialSpec) -> None:
        # Only description is observable from the REST response; the private key and
        # app secrets are not returned by the list API, so key rotation cannot be
        # detected from REST state — that is an accepted limitation.
        if not self._credential_needs_update(observed, spec):
            logger.debug("GitHub credential '%s' is up to date", spec.name)
            return
        params = UpdateGithubCredentialsParams(
            description=spec.description or None,
            app=GithubApp(
                app_id=spec.app_id,
                installation_id=spec.installation_id,
                private_key_bytes=spec.private_key_bytes,
            ),
        )
        logger.info("Updating GitHub credential '%s' (id=%s)", spec.name, observed.id)
        self._client.update_credentials(observed.id, params)

    @staticmethod
    def _credential_needs_update(observed, spec: CredentialSpec) -> bool:
        return observed.description != (spec.description or None)
