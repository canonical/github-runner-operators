# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for garm_api.py."""

from unittest.mock import MagicMock, patch

import pytest

from garm_api import GarmApiClient, GarmApiError, GarmAuthenticatedClient, GarmConnectionError
from garm_client.exceptions import ApiException

BASE_URL = "http://127.0.0.1:9997/api/v1"


def _stub_api_client(client):
    """Patch _api_client on *client* to be a no-op context manager.

    The generated API classes are instantiated with the ApiClient passed as a
    kwarg; by stubbing _api_client we keep those constructors working while
    avoiding real HTTP calls.
    """
    stub = MagicMock()
    stub.__enter__ = MagicMock(return_value=MagicMock())
    stub.__exit__ = MagicMock(return_value=False)
    return patch.object(client, "_api_client", return_value=stub)


@pytest.mark.parametrize(
    "side_effect, expected",
    [
        (None, True),
        (ApiException(status=409), False),
    ],
    ids=["200-ok", "409-not-initialised"],
)
def test_is_initialized(side_effect, expected):
    """
    arrange: GarmApiClient pointed at BASE_URL with a stubbed api_client.
    act: Call is_initialized(); ControllerInfoApi raises ApiException(409) or succeeds.
    assert: Returns True on success, False on 409.
    """
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.ControllerInfoApi") as MockApi:
            if side_effect:
                MockApi.return_value.controller_info.side_effect = side_effect
            result = client.is_initialized()
    assert result is expected


def test_is_initialized_raises_on_unexpected_status():
    """
    arrange: GarmApiClient with ControllerInfoApi raising ApiException(500).
    act: Call is_initialized().
    assert: GarmApiError is raised.
    """
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.ControllerInfoApi") as MockApi:
            MockApi.return_value.controller_info.side_effect = ApiException(status=500)
            with pytest.raises(GarmApiError):
                client.is_initialized()


def test_wait_for_ready_returns_immediately_when_ready():
    """
    arrange: GarmApiClient with is_initialized returning True immediately.
    act: Call wait_for_ready(timeout=5).
    assert: Returns without error and without sleeping.
    """
    client = GarmApiClient(BASE_URL)
    with patch.object(client, "is_initialized", return_value=True):
        client.wait_for_ready(timeout=5)


def test_wait_for_ready_raises_after_timeout():
    """
    arrange: GarmApiClient with is_initialized always raising GarmConnectionError.
    act: Call wait_for_ready(timeout=30) with monotonic clock simulating timeout.
    assert: GarmConnectionError is raised mentioning readiness.
    """
    client = GarmApiClient(BASE_URL)
    with patch.object(client, "is_initialized", side_effect=GarmConnectionError("refused")):
        with patch("garm_api.time.sleep"):
            with patch("garm_api.time.monotonic", side_effect=[0, 0, 100]):
                with pytest.raises(GarmConnectionError, match="ready"):
                    client.wait_for_ready(timeout=30)


def test_first_run_succeeds():
    """
    arrange: GarmApiClient with FirstRunApi returning a mock response.
    act: Call first_run with valid credentials.
    assert: Completes without error.
    """
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.FirstRunApi") as MockApi:
            MockApi.return_value.first_run.return_value = MagicMock()
            client.first_run("admin", "pass", "email@example.com", "Admin")


def test_first_run_raises_on_api_error():
    """
    arrange: GarmApiClient with FirstRunApi raising ApiException(400).
    act: Call first_run with credentials.
    assert: GarmApiError is raised.
    """
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.FirstRunApi") as MockApi:
            MockApi.return_value.first_run.side_effect = ApiException(status=400)
            with pytest.raises(GarmApiError):
                client.first_run("admin", "pass", "email@example.com", "Admin")


def test_login_returns_token():
    """
    arrange: GarmApiClient with LoginApi returning a mock result with token="test-jwt-token".
    act: Call login("admin", "password").
    assert: Returns the token string.
    """
    client = GarmApiClient(BASE_URL)
    mock_result = MagicMock()
    mock_result.token = "test-jwt-token"
    with _stub_api_client(client):
        with patch("garm_api.LoginApi") as MockApi:
            MockApi.return_value.login.return_value = mock_result
            token = client.login("admin", "password")
    assert token == "test-jwt-token"


@pytest.mark.parametrize(
    "token_value, error_type",
    [
        (None, GarmApiError),
        ("", GarmApiError),
    ],
    ids=["none-token", "empty-token"],
)
def test_login_raises_when_token_missing(token_value, error_type):
    """
    arrange: GarmApiClient with LoginApi returning a response with an absent or empty token.
    act: Call login("admin", "password").
    assert: GarmApiError is raised mentioning "token".
    """
    client = GarmApiClient(BASE_URL)
    mock_result = MagicMock()
    mock_result.token = token_value
    with _stub_api_client(client):
        with patch("garm_api.LoginApi") as MockApi:
            MockApi.return_value.login.return_value = mock_result
            with pytest.raises(error_type, match="token"):
                client.login("admin", "password")


def test_login_raises_on_api_error():
    """
    arrange: GarmApiClient with LoginApi raising ApiException(401).
    act: Call login("admin", "wrong").
    assert: GarmApiError is raised.
    """
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.LoginApi") as MockApi:
            MockApi.return_value.login.side_effect = ApiException(
                status=401, reason="Unauthorized"
            )
            with pytest.raises(GarmApiError):
                client.login("admin", "wrong")


def test_authenticated_client_from_login():
    """
    arrange: GarmApiClient.login is patched to return "test-jwt".
    act: Call GarmAuthenticatedClient.from_login(BASE_URL, "admin", "pass").
    assert: Returns a GarmAuthenticatedClient with the token set.
    """
    with patch.object(GarmApiClient, "login", return_value="test-jwt"):
        auth_client = GarmAuthenticatedClient.from_login(BASE_URL, "admin", "pass")
    assert isinstance(auth_client, GarmAuthenticatedClient)
    assert auth_client._token == "test-jwt"


@pytest.mark.parametrize(
    "api_response, expected_names",
    [
        ([("openstack",), ("lxd",)], ["openstack", "lxd"]),
        (None, []),
        ([], []),
    ],
    ids=["two-providers", "none-response", "empty-list"],
)
def test_list_providers(api_response, expected_names):
    """
    arrange: GarmAuthenticatedClient with ProvidersApi returning the parameterised response.
    act: Call list_providers().
    assert: Returns a list of providers with the expected names, or [] when API returns None.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    if api_response is not None:
        mocks = []
        for (name,) in api_response:
            m = MagicMock()
            m.name = name
            mocks.append(m)
        response = mocks
    else:
        response = None
    with _stub_api_client(client):
        with patch("garm_api.ProvidersApi") as MockApi:
            MockApi.return_value.list_providers.return_value = response
            result = client.list_providers()
    assert [p.name for p in result] == expected_names


@pytest.mark.parametrize(
    "api_response, expected_names",
    [
        ([("scaleset-a", 1), ("scaleset-b", 2)], ["scaleset-a", "scaleset-b"]),
        (None, []),
    ],
    ids=["two-scalesets", "none-response"],
)
def test_list_scalesets(api_response, expected_names):
    """
    arrange: GarmAuthenticatedClient with ScalesetsApi returning the parameterised response.
    act: Call list_scalesets().
    assert: Returns a list of scalesets with the expected names, or [] when API returns None.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    if api_response is not None:
        mocks = []
        for name, sid in api_response:
            m = MagicMock()
            m.name = name
            m.id = sid
            mocks.append(m)
        response = mocks
    else:
        response = None
    with _stub_api_client(client):
        with patch("garm_api.ScalesetsApi") as MockApi:
            MockApi.return_value.list_scalesets.return_value = response
            result = client.list_scalesets()
    assert [ss.name for ss in result] == expected_names


@pytest.mark.parametrize(
    "target, registered, expected",
    [
        ("my-org", ["my-org", "other-org"], "org-uuid-123"),
        ("missing-org", ["other-org"], None),
        ("my-org", [], None),
    ],
    ids=["found", "not-found", "empty-list"],
)
def test_find_org_id(target, registered, expected):
    """
    arrange: GarmAuthenticatedClient with OrganizationsApi listing the parameterised orgs.
    act: Call find_org_id(target).
    assert: Returns the UUID when found, None when absent.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mocks = []
    for i, name in enumerate(registered):
        m = MagicMock()
        m.name = name
        m.id = f"org-uuid-{123 + i}" if name == target else f"other-uuid-{i}"
        mocks.append(m)
    with _stub_api_client(client):
        with patch("garm_api.OrganizationsApi") as MockApi:
            MockApi.return_value.list_orgs.return_value = mocks
            result = client.find_org_id(target)
    assert result == expected


@pytest.mark.parametrize(
    "target, registered, expected",
    [
        ("owner/repo", ["owner/repo", "other/repo"], "repo-uuid-123"),
        ("owner/repo", [], None),
    ],
    ids=["found", "not-found"],
)
def test_find_repo_id(target, registered, expected):
    """
    arrange: GarmAuthenticatedClient with RepositoriesApi listing the parameterised repos,
        each repo having separate owner and name fields.
    act: Call find_repo_id(target).
    assert: Returns the UUID when found, None when absent.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mocks = []
    for i, full_name in enumerate(registered):
        owner, name = full_name.split("/", 1)
        m = MagicMock()
        m.owner = owner
        m.name = name
        m.id = f"repo-uuid-{123 + i}" if full_name == target else f"other-uuid-{i}"
        mocks.append(m)
    with _stub_api_client(client):
        with patch("garm_api.RepositoriesApi") as MockApi:
            MockApi.return_value.list_repos.return_value = mocks
            result = client.find_repo_id(target)
    assert result == expected


def test_delete_scaleset_succeeds():
    """
    arrange: GarmAuthenticatedClient with ScalesetsApi stubbed.
    act: Call delete_scaleset(42).
    assert: delete_scale_set is called with scaleset_id="42" and the correct timeout.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.ScalesetsApi") as MockApi:
            client.delete_scaleset(42)
    MockApi.return_value.delete_scale_set.assert_called_once_with(
        scaleset_id="42", _request_timeout=30
    )


def test_delete_scaleset_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with ScalesetsApi raising ApiException(404).
    act: Call delete_scaleset(99).
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.ScalesetsApi") as MockApi:
            MockApi.return_value.delete_scale_set.side_effect = ApiException(status=404)
            with pytest.raises(GarmApiError):
                client.delete_scaleset(99)


def test_list_github_endpoints_returns_list():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi returning one endpoint.
    act: Call list_github_endpoints().
    assert: The returned list carries the endpoint.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mock_ep = MagicMock()
    mock_ep.name = "github.com"
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.list_github_endpoints.return_value = [mock_ep]
            result = client.list_github_endpoints()
    assert len(result) == 1
    assert result[0].name == "github.com"


def test_list_github_endpoints_returns_empty_on_none():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi returning None.
    act: Call list_github_endpoints().
    assert: An empty list is returned.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.list_github_endpoints.return_value = None
            result = client.list_github_endpoints()
    assert result == []


def test_list_github_endpoints_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi raising ApiException(500).
    act: Call list_github_endpoints().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.list_github_endpoints.side_effect = ApiException(status=500)
            with pytest.raises(GarmApiError):
                client.list_github_endpoints()


def test_create_github_endpoint_returns_endpoint():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi returning the created endpoint.
    act: Call create_github_endpoint().
    assert: The created endpoint is returned.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mock_result = MagicMock()
    mock_result.name = "my-enterprise"
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.create_github_endpoint.return_value = mock_result
            result = client.create_github_endpoint(MagicMock())
    assert result.name == "my-enterprise"


def test_create_github_endpoint_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi raising ApiException(400).
    act: Call create_github_endpoint().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.create_github_endpoint.side_effect = ApiException(status=400)
            with pytest.raises(GarmApiError):
                client.create_github_endpoint(MagicMock())


def test_update_github_endpoint_returns_endpoint():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi returning the updated endpoint.
    act: Call update_github_endpoint().
    assert: The updated endpoint is returned.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mock_result = MagicMock()
    mock_result.name = "my-enterprise"
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.update_github_endpoint.return_value = mock_result
            result = client.update_github_endpoint("my-enterprise", MagicMock())
    assert result.name == "my-enterprise"


def test_update_github_endpoint_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi raising ApiException(404).
    act: Call update_github_endpoint().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.update_github_endpoint.side_effect = ApiException(status=404)
            with pytest.raises(GarmApiError):
                client.update_github_endpoint("missing", MagicMock())


def test_delete_github_endpoint_calls_api():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi stubbed.
    act: Call delete_github_endpoint().
    assert: delete_github_endpoint is called once.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            client.delete_github_endpoint("my-enterprise")
    MockApi.return_value.delete_github_endpoint.assert_called_once()


def test_delete_github_endpoint_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with EndpointsApi raising ApiException(404).
    act: Call delete_github_endpoint().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.EndpointsApi") as MockApi:
            MockApi.return_value.delete_github_endpoint.side_effect = ApiException(status=404)
            with pytest.raises(GarmApiError):
                client.delete_github_endpoint("missing")


def test_create_credentials_returns_credentials():
    """
    arrange: GarmAuthenticatedClient with CredentialsApi returning the created credentials.
    act: Call create_credentials().
    assert: The created credentials are returned.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mock_result = MagicMock()
    mock_result.id = 7
    with _stub_api_client(client):
        with patch("garm_api.CredentialsApi") as MockApi:
            MockApi.return_value.create_credentials.return_value = mock_result
            result = client.create_credentials(MagicMock())
    assert result.id == 7


def test_create_credentials_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with CredentialsApi raising ApiException(400).
    act: Call create_credentials().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.CredentialsApi") as MockApi:
            MockApi.return_value.create_credentials.side_effect = ApiException(status=400)
            with pytest.raises(GarmApiError):
                client.create_credentials(MagicMock())


def test_update_credentials_returns_credentials():
    """
    arrange: GarmAuthenticatedClient with CredentialsApi returning the updated credentials.
    act: Call update_credentials().
    assert: The updated credentials are returned.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mock_result = MagicMock()
    mock_result.id = 7
    with _stub_api_client(client):
        with patch("garm_api.CredentialsApi") as MockApi:
            MockApi.return_value.update_credentials.return_value = mock_result
            result = client.update_credentials(7, MagicMock())
    assert result.id == 7


def test_update_credentials_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with CredentialsApi raising ApiException(404).
    act: Call update_credentials().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.CredentialsApi") as MockApi:
            MockApi.return_value.update_credentials.side_effect = ApiException(status=404)
            with pytest.raises(GarmApiError):
                client.update_credentials(99, MagicMock())


def test_delete_credentials_calls_api():
    """
    arrange: GarmAuthenticatedClient with CredentialsApi stubbed.
    act: Call delete_credentials().
    assert: delete_credentials is called once.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.CredentialsApi") as MockApi:
            client.delete_credentials(7)
    MockApi.return_value.delete_credentials.assert_called_once()


def test_delete_credentials_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with CredentialsApi raising ApiException(404).
    act: Call delete_credentials().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.CredentialsApi") as MockApi:
            MockApi.return_value.delete_credentials.side_effect = ApiException(status=404)
            with pytest.raises(GarmApiError):
                client.delete_credentials(99)


def test_update_controller_calls_api():
    """
    arrange: GarmAuthenticatedClient with ControllerApi stubbed.
    act: Call update_controller() with metadata, callback and webhook URLs.
    assert: update_controller is called once.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.ControllerApi") as MockApi:
            client.update_controller(
                metadata_url="http://garm/api/v1/metadata",
                callback_url="http://garm/api/v1/callbacks",
                webhook_url="http://garm/webhooks",
            )
    MockApi.return_value.update_controller.assert_called_once()


def test_update_controller_raises_on_api_error():
    """
    arrange: GarmAuthenticatedClient with ControllerApi raising ApiException(409).
    act: Call update_controller().
    assert: GarmApiError is raised.
    """
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.ControllerApi") as MockApi:
            MockApi.return_value.update_controller.side_effect = ApiException(status=409)
            with pytest.raises(GarmApiError):
                client.update_controller(
                    metadata_url="http://garm/api/v1/metadata",
                    callback_url="http://garm/api/v1/callbacks",
                    webhook_url="http://garm/webhooks",
                )
