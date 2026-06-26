# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GitHub reconciler."""

from unittest.mock import MagicMock, call

from github_reconciler import (
    MANAGED_CREDENTIAL_DESCRIPTION,
    CredentialSpec,
    EndpointSpec,
    GithubReconciler,
)


def _mock_client(endpoints=None, credentials=None):
    """Build a mock GarmAuthenticatedClient with pre-configured list responses."""
    client = MagicMock()

    endpoint_mocks = []
    for ep in endpoints or []:
        m = MagicMock()
        m.name = ep["name"]
        m.base_url = ep.get("base_url", None)
        m.api_base_url = ep.get("api_base_url", None)
        m.upload_base_url = ep.get("upload_base_url", None)
        m.description = ep.get("description", None)
        endpoint_mocks.append(m)
    client.list_github_endpoints.return_value = endpoint_mocks

    credential_mocks = []
    for cred in credentials or []:
        m = MagicMock()
        m.name = cred["name"]
        m.id = cred.get("id", 1)
        m.description = cred.get("description", None)
        credential_mocks.append(m)
    client.list_credentials.return_value = credential_mocks

    return client


def _endpoint_spec(
    name="my-endpoint",
    base_url="https://github.example.com",
    api_base_url="https://api.github.example.com",
    upload_base_url="https://uploads.github.example.com",
    description="",
):
    return EndpointSpec(
        name=name,
        base_url=base_url,
        api_base_url=api_base_url,
        upload_base_url=upload_base_url,
        description=description,
    )


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


def test_create_endpoint_when_missing():
    """
    arrange: A reconciler whose client reports no existing endpoints.
    act: Reconcile a single desired endpoint spec.
    assert: create_github_endpoint is called once with the spec's URLs.
    """
    client = _mock_client(endpoints=[], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_endpoint_spec()], [])
    client.create_github_endpoint.assert_called_once()
    params = client.create_github_endpoint.call_args[0][0]
    assert params.name == "my-endpoint"
    assert params.base_url == "https://github.example.com"
    assert params.api_base_url == "https://api.github.example.com"
    assert params.upload_base_url == "https://uploads.github.example.com"


def test_no_create_or_delete_when_empty():
    """
    arrange: A reconciler whose client reports no existing endpoints or credentials.
    act: Reconcile with empty desired endpoints and credentials.
    assert: No create or delete calls are made.
    """
    client = _mock_client(endpoints=[], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.create_github_endpoint.assert_not_called()
    client.delete_github_endpoint.assert_not_called()
    client.create_credentials.assert_not_called()
    client.delete_credentials.assert_not_called()


def test_endpoints_never_deleted():
    """
    arrange: A client reporting the built-in github.com endpoint plus an operator-configured one.
    act: Reconcile with no desired endpoints.
    assert: delete_github_endpoint is never called — the charm does not own endpoints, so neither
        the built-in github.com nor any operator-configured endpoint is removed.
    """
    client = _mock_client(
        endpoints=[{"name": "github.com"}, {"name": "enterprise-ep"}],
        credentials=[],
    )
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.delete_github_endpoint.assert_not_called()


def test_update_endpoint_when_base_url_changed():
    """
    arrange: A client reporting an endpoint whose base_url differs from the desired spec.
    act: Reconcile the desired endpoint spec.
    assert: update_github_endpoint is called once for that endpoint name.
    """
    existing = {
        "name": "my-endpoint",
        "base_url": "https://old.example.com",
        "api_base_url": "https://api.github.example.com",
        "upload_base_url": "https://uploads.github.example.com",
        "description": None,
    }
    client = _mock_client(endpoints=[existing], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_endpoint_spec(base_url="https://new.example.com")], [])
    client.update_github_endpoint.assert_called_once()
    name_arg = client.update_github_endpoint.call_args[0][0]
    assert name_arg == "my-endpoint"


def test_no_update_endpoint_when_unchanged():
    """
    arrange: A client reporting an endpoint identical to the desired spec.
    act: Reconcile the desired endpoint spec.
    assert: Neither update_github_endpoint nor create_github_endpoint is called.
    """
    existing = {
        "name": "my-endpoint",
        "base_url": "https://github.example.com",
        "api_base_url": "https://api.github.example.com",
        "upload_base_url": "https://uploads.github.example.com",
        "description": None,
    }
    client = _mock_client(endpoints=[existing], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([_endpoint_spec()], [])
    client.update_github_endpoint.assert_not_called()
    client.create_github_endpoint.assert_not_called()


def test_create_credential_when_missing():
    """
    arrange: A reconciler whose client reports no existing credentials.
    act: Reconcile a single desired App credential spec.
    assert: create_credentials is called once with the spec's app auth fields.
    """
    client = _mock_client(endpoints=[], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [_cred_spec()])
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
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [_cred_spec(description=MANAGED_CREDENTIAL_DESCRIPTION)])
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
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile(
        [], [_cred_spec(name="app-1-2", description=MANAGED_CREDENTIAL_DESCRIPTION)]
    )
    client.update_credentials.assert_not_called()


def test_no_update_credential_when_unchanged():
    """
    arrange: A client reporting a credential with no description.
    act: Reconcile a desired credential with description="" (which maps to None, matching observed).
    assert: Neither update_credentials nor create_credentials is called.
    """
    existing = {"name": "my-cred", "id": 7, "description": None}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [_cred_spec(description="")])
    client.update_credentials.assert_not_called()
    client.create_credentials.assert_not_called()


def test_delete_managed_orphan_credential():
    """
    arrange: A client reporting a managed credential that is absent from the desired set.
    act: Reconcile with no desired credentials.
    assert: delete_credentials is called once with the orphan's id.
    """
    existing = {"name": "stale-cred", "id": 42, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.delete_credentials.assert_called_once_with(42)


def test_unmanaged_orphan_credential_preserved():
    """
    arrange: A client reporting a credential without the managed marker (e.g. an operator PAT).
    act: Reconcile with no desired credentials.
    assert: delete_credentials is not called — unmanaged credentials are never deleted.
    """
    existing = {"name": "operator-pat", "id": 99, "description": "set up by hand"}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.delete_credentials.assert_not_called()


def test_nameless_observed_credential_ignored():
    """
    arrange: A client reporting a managed credential that GARM returns without a name.
    act: Reconcile with no desired credentials.
    assert: delete_credentials is not called — a nameless credential must not become a None map
        key or be treated as a managed orphan.
    """
    existing = {"name": None, "id": 5, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.delete_credentials.assert_not_called()


def test_update_skipped_when_observed_credential_has_no_id():
    """
    arrange: A client reporting a managed credential whose id is None.
    act: Reconcile a desired credential of the same name with a changed description.
    assert: update_credentials is not called — there is no id to update against.
    """
    existing = {"name": "app-1-2", "id": None, "description": MANAGED_CREDENTIAL_DESCRIPTION}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [_cred_spec(name="app-1-2", description="new description")])
    client.update_credentials.assert_not_called()


def test_endpoints_reconciled_before_credentials():
    """
    arrange: A shared parent mock recording all client calls, with one desired endpoint and
        one desired credential.
    act: Reconcile both.
    assert: The endpoint call is recorded before the credential call (credentials may reference
        endpoints, so endpoints must exist first).
    """
    parent = MagicMock()
    parent.list_github_endpoints.return_value = []
    parent.list_credentials.return_value = []

    reconciler = GithubReconciler(parent)
    reconciler.reconcile([_endpoint_spec()], [_cred_spec()])

    method_names = [c[0] for c in parent.method_calls]
    ep_index = next(i for i, n in enumerate(method_names) if "endpoint" in n)
    cred_index = next(
        i for i, n in enumerate(method_names) if "credential" in n or n == "create_credentials"
    )
    assert ep_index < cred_index
