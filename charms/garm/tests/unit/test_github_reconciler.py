# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GitHub reconciler."""

from unittest.mock import MagicMock

from garm_api import GarmApiError
from github_reconciler import MANAGED_CREDENTIAL_DESCRIPTION, CredentialSpec, GithubReconciler


def _mock_client(credentials=None):
    """Build a mock GarmAuthenticatedClient with a pre-configured credential list response."""
    client = MagicMock()

    credential_mocks = []
    for cred in credentials or []:
        m = MagicMock()
        m.name = cred["name"]
        m.id = cred.get("id", 1)
        m.description = cred.get("description", None)
        credential_mocks.append(m)
    client.list_credentials.return_value = credential_mocks

    return client


def _cred_spec(
    name="my-cred",
    endpoint="github.com",
    app_id=123,
    installation_id=456,
    private_key_bytes=None,
    description="",
):
    return CredentialSpec(
        name=name,
        endpoint=endpoint,
        app_id=app_id,
        installation_id=installation_id,
        private_key_bytes=private_key_bytes or [1, 2, 3],
        description=description,
    )


def test_no_create_or_delete_when_empty():
    """
    arrange: A reconciler whose client reports no existing credentials.
    act: Reconcile with empty desired credentials.
    assert: No create or delete calls are made.
    """
    client = _mock_client(credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([])
    client.create_credentials.assert_not_called()
    client.delete_credentials.assert_not_called()


def test_create_credential_when_missing():
    """
    arrange: A reconciler whose client reports no existing credentials.
    act: Reconcile a single desired App credential spec.
    assert: create_credentials is called once with the spec's app auth fields.
    """
    client = _mock_client(credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_cred_spec()])
    client.create_credentials.assert_called_once()
    params = client.create_credentials.call_args[0][0]
    assert params.name == "my-cred"
    assert params.auth_type == "app"
    assert params.endpoint == "github.com"
    assert params.app.app_id == 123
    assert params.app.installation_id == 456
    assert params.app.private_key_bytes == [1, 2, 3]


def test_update_adoptable_credential_when_description_changed():
    """
    arrange: A client reporting a credential with no description (unclaimed, so adoptable).
    act: Reconcile a desired credential carrying the managed description.
    assert: update_credentials is called once for that credential id.
    """
    existing = {"name": "my-cred", "id": 7, "description": None}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_cred_spec(description=MANAGED_CREDENTIAL_DESCRIPTION)])
    client.update_credentials.assert_called_once()
    assert client.update_credentials.call_args[0][0] == 7


def test_update_skipped_for_unmanaged_credential():
    """
    arrange: A client reporting a credential whose description marks it operator-owned, with a
        name matching a desired credential.
    act: Reconcile the desired managed credential of the same name.
    assert: update_credentials is not called — operator-owned credentials are never overwritten.
    """
    existing = {"name": "app-1-2", "id": 7, "description": "operator owned"}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_cred_spec(name="app-1-2", description=MANAGED_CREDENTIAL_DESCRIPTION)])
    client.update_credentials.assert_not_called()


def test_no_update_credential_when_unchanged():
    """
    arrange: A client reporting a credential with no description.
    act: Reconcile a desired credential with description="" (which maps to None, matching observed).
    assert: Neither update_credentials nor create_credentials is called.
    """
    existing = {"name": "my-cred", "id": 7, "description": None}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_cred_spec(description="")])
    client.update_credentials.assert_not_called()
    client.create_credentials.assert_not_called()


def test_delete_managed_orphan_credential():
    """
    arrange: A client reporting a managed credential that is absent from the desired set.
    act: Reconcile with no desired credentials.
    assert: delete_credentials is called once with the orphan's id.
    """
    existing = {"name": "stale-cred", "id": 42, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([])
    client.delete_credentials.assert_called_once_with(42)


def test_unmanaged_orphan_credential_preserved():
    """
    arrange: A client reporting a credential without the managed marker (e.g. an operator PAT).
    act: Reconcile with no desired credentials.
    assert: delete_credentials is not called — unmanaged credentials are never deleted.
    """
    existing = {"name": "operator-pat", "id": 99, "description": "set up by hand"}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([])
    client.delete_credentials.assert_not_called()


def test_nameless_observed_credential_ignored():
    """
    arrange: A client reporting a managed credential that GARM returns without a name.
    act: Reconcile with no desired credentials.
    assert: delete_credentials is not called — a nameless credential must not become a None map
        key or be treated as a managed orphan.
    """
    existing = {"name": None, "id": 5, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([])
    client.delete_credentials.assert_not_called()


def test_orphan_credential_delete_is_non_fatal():
    """
    arrange: A managed orphan credential whose deletion raises GarmApiError (an entity still
        references it).
    act: Reconcile with no desired credentials.
    assert: reconcile swallows the error so the pass continues; delete_credentials was attempted.
    """
    existing = {"name": "stale-cred", "id": 42, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(credentials=[existing])
    client.delete_credentials.side_effect = GarmApiError("credential still in use")
    reconciler = GithubReconciler(client)

    reconciler.reconcile([])  # must not raise

    client.delete_credentials.assert_called_once_with(42)


def test_update_skipped_when_observed_credential_has_no_id():
    """
    arrange: A client reporting a managed credential whose id is None.
    act: Reconcile a desired credential of the same name with a changed description.
    assert: update_credentials is not called — there is no id to update against.
    """
    existing = {"name": "app-1-2", "id": None, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_cred_spec(name="app-1-2", description="new description")])
    client.update_credentials.assert_not_called()
