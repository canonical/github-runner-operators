# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Entity reconciler: registers GARM org/repo entities so scalesets can be created under them.

GARM requires an organization/repository entity (linked to a GitHub credential) to exist before a
scaleset can be created under it. This reconciler sits between the credential reconciler and the
scaleset reconciler: credentials are created first, the entity references a credential by name, and
the scaleset reconciler then resolves the entity id. An entity is owned by the charm when it is
bound to a charm-managed credential; only owned entities are updated or deleted.
"""

import logging
import secrets
from dataclasses import dataclass

from garm_api import GarmApiError, GarmAuthenticatedClient
from garm_client.models.create_org_params import CreateOrgParams
from garm_client.models.create_repo_params import CreateRepoParams
from garm_client.models.update_entity_params import UpdateEntityParams
from github_reconciler import MANAGED_CREDENTIAL_DESCRIPTION

logger = logging.getLogger(__name__)


@dataclass
class EntitySpec:
    """Desired state for one GARM entity (organization or repository)."""

    entity_type: str  # "organization" | "repository"
    entity_name: str  # org name, or "owner/repo"
    credentials_name: str  # "app-<app_id>-<installation_id>"


class EntityReconciler:
    """Reconciles GARM org/repo entities against a desired spec list."""

    def __init__(self, client: GarmAuthenticatedClient, agent_mode: bool | None = None) -> None:
        """Initialise the reconciler.

        Args:
            client: Authenticated GarmAuthenticatedClient instance.
            agent_mode: Whether entities should run their runners in GARM agent mode, or
                None to leave the current setting alone. None is used when the charm has
                not been able to confirm that the garm-agent binaries are published:
                enabling agent mode without them makes GARM hand runners a github.com
                download URL, and toggling it off on every unconfirmed pass would churn
                the entities instead.
        """
        self._client = client
        self._agent_mode = agent_mode

    def reconcile(self, desired: list[EntitySpec]) -> None:
        """Register, update, or delete GARM entities to match *desired*.

        Credentials are resolved by id so charm ownership can be attributed (an entity bound to a
        charm-managed credential is owned by the charm). Both registration and deletion are
        best-effort and deferred on failure: GARM validates an entity against GitHub when
        registering it, and rejects deleting one while scalesets still reference it, so each is
        retried on the next reconcile rather than aborting the pass or blocking other entities.

        Args:
            desired: The full desired set of entities across all configurator relations.
        """
        creds_by_id = {c.id: c for c in self._client.list_credentials() if c.id is not None}

        self._reconcile_orgs(
            {s.entity_name: s for s in desired if s.entity_type == "organization"}, creds_by_id
        )
        self._reconcile_repos(
            {s.entity_name: s for s in desired if s.entity_type == "repository"}, creds_by_id
        )

    def _reconcile_orgs(self, desired: dict[str, EntitySpec], creds_by_id: dict) -> None:
        observed = {org.name: org for org in self._client.list_orgs() if org.name}

        for name, spec in desired.items():
            existing = observed.get(name)
            try:
                if existing is None:
                    logger.info(
                        "Creating organization registration in GARM database: name='%s'", name
                    )
                    self._client.create_org(
                        CreateOrgParams(
                            name=name,
                            credentials_name=spec.credentials_name,
                            agent_mode=self._agent_mode,
                            # GARM rejects registration without a non-empty webhook_secret;
                            # the charm never installs a webhook, so this value is unused.
                            webhook_secret=_random_webhook_secret(),
                        )
                    )
                elif existing.id and (
                    update := self._entity_update(existing, spec, creds_by_id, name)
                ):
                    logger.info(
                        "Updating organization registration in GARM database: "
                        "name='%s', fields=%s",
                        name,
                        sorted(update.to_dict()),
                    )
                    self._client.update_org(existing.id, update)
            except GarmApiError as exc:
                self._log_deferred("organization", name, exc)

        for name, org in observed.items():
            if name not in desired and org.id and self._is_managed(org, creds_by_id):
                self._safe_delete(self._client.delete_org, org.id, "organization", name)

    def _reconcile_repos(self, desired: dict[str, EntitySpec], creds_by_id: dict) -> None:
        observed = {
            f"{repo.owner}/{repo.name}": repo
            for repo in self._client.list_repos()
            if repo.owner and repo.name
        }

        for full_name, spec in desired.items():
            existing = observed.get(full_name)
            try:
                if existing is None:
                    owner, _, name = full_name.partition("/")
                    if not (owner and name):
                        logger.warning(
                            "Skipping repository registration in GARM database: name='%s'; "
                            "expected 'owner/repo' format",
                            full_name,
                        )
                        continue
                    logger.info(
                        "Creating repository registration in GARM database: name='%s'", full_name
                    )
                    self._client.create_repo(
                        CreateRepoParams(
                            owner=owner,
                            name=name,
                            credentials_name=spec.credentials_name,
                            agent_mode=self._agent_mode,
                            # GARM rejects registration without a non-empty webhook_secret;
                            # the charm never installs a webhook, so this value is unused.
                            webhook_secret=_random_webhook_secret(),
                        )
                    )
                elif existing.id and (
                    update := self._entity_update(existing, spec, creds_by_id, full_name)
                ):
                    logger.info(
                        "Updating repository registration in GARM database: name='%s', fields=%s",
                        full_name,
                        sorted(update.to_dict()),
                    )
                    self._client.update_repo(existing.id, update)
            except GarmApiError as exc:
                self._log_deferred("repository", full_name, exc)

        for full_name, repo in observed.items():
            if full_name not in desired and repo.id and self._is_managed(repo, creds_by_id):
                self._safe_delete(self._client.delete_repo, repo.id, "repository", full_name)

    def _entity_update(
        self, observed, spec: EntitySpec, creds_by_id: dict, name: str
    ) -> UpdateEntityParams | None:
        """Build the update needed to bring *observed* in line with the desired state.

        Only the drifted fields are sent: every field of ``UpdateEntityParams`` is omitted
        when empty, so a partial update cannot clear the entity's credentials or webhook
        secret.

        Args:
            observed: The entity as GARM currently holds it.
            spec: The desired state for that entity.
            creds_by_id: Credentials indexed by id, used to resolve ownership.
            name: The entity's display name, for logging.

        Returns:
            The update to apply, or None if the entity already matches.
        """
        update = UpdateEntityParams()
        if self._needs_credential_update(observed, spec, creds_by_id, name):
            update.credentials_name = spec.credentials_name
        if self._agent_mode is not None and bool(observed.agent_mode) != self._agent_mode:
            update.agent_mode = self._agent_mode
        return update if update.to_dict() else None

    @staticmethod
    def _needs_credential_update(observed, spec: EntitySpec, creds_by_id: dict, name: str) -> bool:
        """Return True if *observed*'s credential differs from the spec and is safe to change.

        An entity bound to an operator-owned (unmanaged) credential is never overwritten; one with
        no resolvable credential is unclaimed and safe to adopt.
        """
        current = creds_by_id.get(observed.credentials_id)
        if (current.name if current else None) == spec.credentials_name:
            return False
        if current is not None and current.description != MANAGED_CREDENTIAL_DESCRIPTION:
            logger.warning(
                "Skipping credential update for entity registration in GARM database: "
                "name='%s', unmanaged credential='%s'",
                name,
                current.name,
            )
            return False
        return True

    @staticmethod
    def _is_managed(entity, creds_by_id: dict) -> bool:
        # An entity is charm-owned when it is bound to a charm-managed credential. This relies on
        # GARM rejecting deletion of a credential still referenced by an entity, so the managed
        # credential outlives the entity during teardown and ownership stays attributable.
        current = creds_by_id.get(entity.credentials_id)
        return current is not None and current.description == MANAGED_CREDENTIAL_DESCRIPTION

    @staticmethod
    def _log_deferred(kind: str, name: str, exc: GarmApiError) -> None:
        # Registration goes through GitHub (GARM validates the entity against the forge), so a
        # transient GitHub/credential issue must not abort the whole reconcile or block scalesets
        # for other entities. Defer like the scaleset reconciler does and retry on the next pass.
        logger.warning(
            "Deferring %s registration operation in GARM database: name='%s' "
            "(GARM could not complete it yet; will retry): %s",
            kind,
            name,
            exc,
        )

    @staticmethod
    def _safe_delete(delete_fn, entity_id, kind: str, name: str) -> None:
        logger.info(
            "Deleting orphaned %s registration from GARM database: name='%s', id=%s",
            kind,
            name,
            entity_id,
        )
        try:
            delete_fn(entity_id)
        except GarmApiError as exc:
            logger.warning(
                "Could not delete %s registration from GARM database: name='%s' (scalesets may "
                "still reference it; will retry): %s",
                kind,
                name,
                exc,
            )


def _random_webhook_secret() -> str:
    """Return a fresh random webhook secret."""
    return secrets.token_hex(32)
