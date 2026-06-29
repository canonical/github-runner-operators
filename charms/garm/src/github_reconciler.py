#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GitHub reconciler: diffs desired vs observed GARM GitHub credentials."""

import logging
from dataclasses import dataclass, field

from garm_api import GarmAuthenticatedClient
from garm_client.models.create_github_credentials_params import CreateGithubCredentialsParams
from garm_client.models.github_app import GithubApp
from garm_client.models.update_github_credentials_params import UpdateGithubCredentialsParams

logger = logging.getLogger(__name__)

# GARM's built-in GitHub endpoint that all managed credentials attach to. Only github.com is
# supported; custom (e.g. GitHub Enterprise) endpoints are not configurable by this charm.
DEFAULT_GITHUB_ENDPOINT = "github.com"

# Description stamped on credentials this charm manages. Reconcile only deletes credentials
# carrying this marker, so operator- or otherwise out-of-band-managed credentials are left alone.
MANAGED_CREDENTIAL_DESCRIPTION = "Managed by garm-configurator"


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
    """Reconciles GARM GitHub credentials against a desired spec list."""

    def __init__(self, client: GarmAuthenticatedClient) -> None:
        """Initialise the reconciler.

        Args:
            client: Authenticated GarmAuthenticatedClient instance.
        """
        self._client = client

    def reconcile(self, credentials: list[CredentialSpec]) -> None:
        """Sync GARM GitHub credentials to match the desired state.

        Credentials attach to GARM's built-in github.com endpoint. Performs the minimum
        set of CREATE / UPDATE / DELETE operations.

        Args:
            credentials: The full desired set of GitHub credentials.
        """
        self._reconcile_credentials(credentials)

    def _reconcile_credentials(self, desired: list[CredentialSpec]) -> None:
        observed = {c.name: c for c in self._client.list_credentials() if c.name}
        desired_names = {spec.name for spec in desired}

        for spec in desired:
            if spec.name not in observed:
                self._create_credential(spec)
                continue
            cred = observed[spec.name]
            if not self._is_charm_managed(cred):
                logger.warning(
                    "Skipping GitHub credential '%s': the name is already used by a credential "
                    "this charm does not manage",
                    spec.name,
                )
                continue
            self._maybe_update_credential(cred, spec)

        for name, cred in observed.items():
            if (
                name not in desired_names
                and cred.id is not None
                and cred.description == MANAGED_CREDENTIAL_DESCRIPTION
            ):
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
        if observed.id is None:
            logger.warning(
                "Cannot update GitHub credential '%s': observed id is missing", spec.name
            )
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
    def _is_charm_managed(cred) -> bool:
        # A credential carrying the managed marker was created by this charm; one with no
        # description is unclaimed and safe to adopt. Any other description is operator-owned,
        # so we never update or overwrite it.
        return cred.description in (MANAGED_CREDENTIAL_DESCRIPTION, None, "")

    @staticmethod
    def _credential_needs_update(observed, spec: CredentialSpec) -> bool:
        # Only diff the description when the spec sets one, so an empty description does not
        # trigger no-op updates (UpdateGithubCredentialsParams omits None fields when serialized).
        return bool(spec.description) and observed.description != spec.description
