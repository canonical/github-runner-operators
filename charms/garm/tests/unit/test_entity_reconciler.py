# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the entity reconciler."""

from unittest.mock import MagicMock

import pytest

from entity_reconciler import EntityReconciler, EntitySpec
from garm_api import GarmApiError
from github_reconciler import MANAGED_CREDENTIAL_DESCRIPTION

MANAGED_CRED = {"id": 1, "name": "app-1-2", "description": MANAGED_CREDENTIAL_DESCRIPTION}
UNMANAGED_CRED = {"id": 2, "name": "op-cred", "description": "operator owned"}


def _attrs(**kwargs):
    m = MagicMock()
    for key, value in kwargs.items():
        setattr(m, key, value)
    return m


def _client(credentials=None, orgs=None, repos=None):
    """Build a mock GarmAuthenticatedClient with pre-configured list responses."""
    client = MagicMock()
    client.list_credentials.return_value = [_attrs(**c) for c in (credentials or [MANAGED_CRED])]
    client.list_orgs.return_value = [_attrs(**o) for o in (orgs or [])]
    client.list_repos.return_value = [_attrs(**r) for r in (repos or [])]
    return client


def _reconcile(client, desired):
    EntityReconciler(client).reconcile(desired)


def test_create_org_when_missing():
    """
    arrange: A client with the managed credential and no registered orgs.
    act: Reconcile a desired organization entity.
    assert: create_org is called once with the org name and managed credential; no update/delete.
    """
    client = _client(orgs=[])
    _reconcile(client, [EntitySpec("organization", "canonical", "app-1-2")])

    client.create_org.assert_called_once()
    params = client.create_org.call_args[0][0]
    assert params.name == "canonical"
    assert params.credentials_name == "app-1-2"
    client.update_org.assert_not_called()
    client.delete_org.assert_not_called()


def test_create_repo_splits_owner_and_name():
    """
    arrange: A client with the managed credential and no registered repos.
    act: Reconcile a desired repository entity named "owner/repo".
    assert: create_repo is called once with owner and name split apart.
    """
    client = _client(repos=[])
    _reconcile(client, [EntitySpec("repository", "canonical/runner", "app-1-2")])

    client.create_repo.assert_called_once()
    params = client.create_repo.call_args[0][0]
    assert params.owner == "canonical"
    assert params.name == "runner"
    assert params.credentials_name == "app-1-2"


def test_no_op_when_org_present_and_credential_matches():
    """
    arrange: A client with an org already bound to the desired managed credential.
    act: Reconcile the same desired organization.
    assert: No create, update, or delete is issued.
    """
    org = {"name": "canonical", "id": "org-uuid", "credentials_id": 1}
    client = _client(orgs=[org])
    _reconcile(client, [EntitySpec("organization", "canonical", "app-1-2")])

    client.create_org.assert_not_called()
    client.update_org.assert_not_called()
    client.delete_org.assert_not_called()


def test_update_org_when_credential_drifts():
    """
    arrange: An org bound to a managed credential whose name differs from the desired one.
    act: Reconcile the org with a different (desired) credential name.
    assert: update_org is called once with the org id and the new credential name.
    """
    managed_other = {"id": 1, "name": "app-9-9", "description": MANAGED_CREDENTIAL_DESCRIPTION}
    org = {"name": "canonical", "id": "org-uuid", "credentials_id": 1}
    client = _client(credentials=[managed_other], orgs=[org])
    _reconcile(client, [EntitySpec("organization", "canonical", "app-1-2")])

    client.update_org.assert_called_once()
    org_id, params = client.update_org.call_args[0]
    assert org_id == "org-uuid"
    assert params.credentials_name == "app-1-2"


def test_update_repo_when_credential_drifts():
    """
    arrange: A repo bound to a managed credential whose name differs from the desired one.
    act: Reconcile the repo with a different (desired) credential name.
    assert: update_repo is called once with the repo id and the new credential name.
    """
    managed_other = {"id": 1, "name": "app-9-9", "description": MANAGED_CREDENTIAL_DESCRIPTION}
    repo = {"owner": "canonical", "name": "runner", "id": "repo-uuid", "credentials_id": 1}
    client = _client(credentials=[managed_other], repos=[repo])
    _reconcile(client, [EntitySpec("repository", "canonical/runner", "app-1-2")])

    client.update_repo.assert_called_once()
    repo_id, params = client.update_repo.call_args[0]
    assert repo_id == "repo-uuid"
    assert params.credentials_name == "app-1-2"


def test_update_skipped_for_unmanaged_credential():
    """
    arrange: An org bound to an operator-owned (unmanaged) credential.
    act: Reconcile the org with a different desired credential.
    assert: update_org is not called — operator-owned bindings are never overwritten.
    """
    org = {"name": "canonical", "id": "org-uuid", "credentials_id": 2}
    client = _client(credentials=[UNMANAGED_CRED], orgs=[org])
    _reconcile(client, [EntitySpec("organization", "canonical", "app-1-2")])

    client.update_org.assert_not_called()


@pytest.mark.parametrize(
    "credentials, credentials_id, expect_deleted",
    [
        ([MANAGED_CRED], 1, True),
        ([UNMANAGED_CRED], 2, False),
        ([MANAGED_CRED], None, False),
    ],
    ids=["managed-deleted", "unmanaged-kept", "no-credential-kept"],
)
def test_orphan_org_deletion_respects_ownership(credentials, credentials_id, expect_deleted):
    """
    arrange: A client with an orphan org bound to a managed, unmanaged, or absent credential.
    act: Reconcile with no desired entities.
    assert: Only a charm-managed orphan is deleted; others are preserved.
    """
    org = {"name": "stale", "id": "org-uuid", "credentials_id": credentials_id}
    client = _client(credentials=credentials, orgs=[org])
    _reconcile(client, [])

    assert client.delete_org.called is expect_deleted


def test_delete_orphan_repo_when_managed():
    """
    arrange: A client with an orphan repo bound to the managed credential.
    act: Reconcile with no desired entities.
    assert: delete_repo is called once with the repo id.
    """
    repo = {"owner": "canonical", "name": "runner", "id": "repo-uuid", "credentials_id": 1}
    client = _client(repos=[repo])
    _reconcile(client, [])

    client.delete_repo.assert_called_once_with("repo-uuid")


def test_create_failure_is_deferred_not_fatal():
    """
    arrange: Two desired orgs where registering the first raises GarmApiError (GARM cannot reach
        GitHub yet).
    act: Reconcile both.
    assert: reconcile swallows the error and still attempts the second org — one bad entity does
        not abort the pass or block the others.
    """
    client = _client(orgs=[])
    client.create_org.side_effect = [GarmApiError("500 server error"), None]

    _reconcile(
        client,
        [
            EntitySpec("organization", "canonical", "app-1-2"),
            EntitySpec("organization", "other", "app-1-2"),
        ],
    )

    assert client.create_org.call_count == 2


def test_orphan_delete_is_non_fatal():
    """
    arrange: A managed orphan org whose deletion raises GarmApiError (scalesets still reference it).
    act: Reconcile with no desired entities.
    assert: reconcile swallows the error so the pass continues; delete_org was attempted once.
    """
    org = {"name": "stale", "id": "org-uuid", "credentials_id": 1}
    client = _client(orgs=[org])
    client.delete_org.side_effect = GarmApiError("entity still has scalesets")

    _reconcile(client, [])  # must not raise

    client.delete_org.assert_called_once_with("org-uuid")
