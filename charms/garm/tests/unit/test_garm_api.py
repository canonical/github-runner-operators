# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for garm_api.py."""

from unittest.mock import MagicMock, patch

import pytest

from garm_api import GarmApiClient, GarmApiError, GarmAuthenticatedClient, GarmConnectionError
from garm_client.exceptions import ApiException

BASE_URL = "http://127.0.0.1:9997/api/v1"


@pytest.fixture(name="client")
def client_fixture():
    """Provide a GarmApiClient pointed at BASE_URL."""
    return GarmApiClient(BASE_URL)


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


class TestIsInitialized:
    """Tests for GarmApiClient.is_initialized grouped for node-ID compatibility."""

    def test_returns_true_when_controller_info_succeeds(self, client):
        """is_initialized returns True when controller_info returns 200."""
        with patch("garm_api.ControllerInfoApi") as mock_cls:
            mock_cls.return_value.controller_info.return_value = MagicMock()
            assert client.is_initialized() is True

    def test_returns_false_on_409(self, client):
        """is_initialized returns False when GARM returns 409 (not yet initialised)."""
        with patch("garm_api.ControllerInfoApi") as mock_cls:
            mock_cls.return_value.controller_info.side_effect = ApiException(status=409)
            assert client.is_initialized() is False

    def test_raises_garm_api_error_on_unexpected_status(self, client):
        """is_initialized raises GarmApiError on unexpected HTTP status."""
        with patch("garm_api.ControllerInfoApi") as mock_cls:
            mock_cls.return_value.controller_info.side_effect = ApiException(status=500)
            with pytest.raises(GarmApiError, match="500"):
                client.is_initialized()


class TestFirstRun:
    """Tests for GarmApiClient.first_run grouped for node-ID compatibility."""

    def test_calls_api_with_correct_params(self, client):
        """first_run passes correct parameters to the underlying API."""
        with patch("garm_api.FirstRunApi") as mock_cls:
            mock_cls.return_value.first_run.return_value = MagicMock()
            client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")
        body = mock_cls.return_value.first_run.call_args.kwargs["body"]
        assert body.username == "admin"
        assert body.email == "admin@test.local"

    def test_raises_garm_api_error_on_failure(self, client):
        """first_run raises GarmApiError when the API returns an error."""
        with patch("garm_api.FirstRunApi") as mock_cls:
            mock_cls.return_value.first_run.side_effect = ApiException(status=400)
            with pytest.raises(GarmApiError, match="400"):
                client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")


class TestLogin:
    """Tests for GarmApiClient.login."""

    def test_returns_jwt_token(self, client):
        """
        arrange: LoginApi.login returns a JWTResponse with a token.
        act: Call client.login().
        assert: The returned token matches the mock value.
        """
        mock_response = MagicMock()
        mock_response.token = "jwt-test-token"
        with patch("garm_api.LoginApi") as mock_cls:
            mock_cls.return_value.login.return_value = mock_response
            token = client.login("admin", "Password-123!")
        assert token == "jwt-test-token"

    def test_raises_garm_api_error_on_failure(self, client):
        """
        arrange: LoginApi.login raises ApiException with status 401.
        act: Call client.login().
        assert: Raises GarmApiError with the status code in the message.
        """
        with patch("garm_api.LoginApi") as mock_cls:
            mock_cls.return_value.login.side_effect = ApiException(status=401)
            with pytest.raises(GarmApiError, match="401"):
                client.login("admin", "wrong-password")


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
