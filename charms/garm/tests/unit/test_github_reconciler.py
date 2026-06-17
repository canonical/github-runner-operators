# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GitHub reconciler."""

from unittest.mock import MagicMock, call

from github_reconciler import CredentialSpec, EndpointSpec, GithubReconciler


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
    client = _mock_client(endpoints=[], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.create_github_endpoint.assert_not_called()
    client.delete_github_endpoint.assert_not_called()
    client.create_credentials.assert_not_called()
    client.delete_credentials.assert_not_called()


def test_builtin_github_endpoint_never_deleted():
    # Even when desired endpoints don't include github.com, it must not be deleted.
    client = _mock_client(
        endpoints=[{"name": "github.com"}, {"name": "orphan-ep"}],
        credentials=[],
    )
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    deleted_names = [c.args[0] for c in client.delete_github_endpoint.call_args_list]
    assert "github.com" not in deleted_names
    assert "orphan-ep" in deleted_names


def test_delete_orphan_endpoint_not_in_desired():
    client = _mock_client(endpoints=[{"name": "stale-ep"}], credentials=[])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.delete_github_endpoint.assert_called_once_with("stale-ep")


def test_update_endpoint_when_base_url_changed():
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


def test_update_credential_when_description_changed():
    existing = {"name": "my-cred", "id": 7, "description": "old description"}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [_cred_spec(description="new description")])
    client.update_credentials.assert_called_once()
    id_arg = client.update_credentials.call_args[0][0]
    assert id_arg == 7


def test_no_update_credential_when_unchanged():
    existing = {"name": "my-cred", "id": 7, "description": None}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    # description="" maps to None, so this matches the observed None
    reconciler.reconcile([], [_cred_spec(description="")])
    client.update_credentials.assert_not_called()
    client.create_credentials.assert_not_called()


def test_delete_orphan_credential_not_in_desired():
    existing = {"name": "stale-cred", "id": 42, "description": None}
    client = _mock_client(endpoints=[], credentials=[existing])
    reconciler = GithubReconciler(client)
    reconciler.reconcile([], [])
    client.delete_credentials.assert_called_once_with(42)


def test_endpoints_reconciled_before_credentials():
    # Record the call order on a shared parent mock to verify endpoints come first.
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
