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


# ---------------------------------------------------------------------------
# GarmApiClient.is_initialized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "side_effect, expected",
    [
        (None, True),
        (ApiException(status=409), False),
    ],
    ids=["200-ok", "409-not-initialised"],
)
def test_is_initialized(side_effect, expected):
    """is_initialized returns True on 200 and False on 409."""
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.ControllerInfoApi") as MockApi:
            if side_effect:
                MockApi.return_value.controller_info.side_effect = side_effect
            result = client.is_initialized()
    assert result is expected


def test_is_initialized_raises_on_unexpected_status():
    """is_initialized raises GarmApiError for any status other than 200/409."""
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.ControllerInfoApi") as MockApi:
            MockApi.return_value.controller_info.side_effect = ApiException(status=500)
            with pytest.raises(GarmApiError):
                client.is_initialized()


# ---------------------------------------------------------------------------
# GarmApiClient.wait_for_ready
# ---------------------------------------------------------------------------


def test_wait_for_ready_returns_immediately_when_ready():
    """wait_for_ready returns without sleeping when GARM is already up."""
    client = GarmApiClient(BASE_URL)
    with patch.object(client, "is_initialized", return_value=True):
        client.wait_for_ready(timeout=5)


def test_wait_for_ready_raises_after_timeout():
    """wait_for_ready raises GarmConnectionError when GARM never responds."""
    client = GarmApiClient(BASE_URL)
    with patch.object(client, "is_initialized", side_effect=GarmConnectionError("refused")):
        with patch("garm_api.time.sleep"):
            with patch("garm_api.time.monotonic", side_effect=[0, 0, 100]):
                with pytest.raises(GarmConnectionError, match="ready"):
                    client.wait_for_ready(timeout=30)


# ---------------------------------------------------------------------------
# GarmApiClient.first_run
# ---------------------------------------------------------------------------


def test_first_run_succeeds():
    """first_run completes without error on a successful API response."""
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.FirstRunApi") as MockApi:
            MockApi.return_value.first_run.return_value = MagicMock()
            client.first_run("admin", "pass", "email@example.com", "Admin")


def test_first_run_raises_on_api_error():
    """first_run raises GarmApiError when the API returns an error status."""
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.FirstRunApi") as MockApi:
            MockApi.return_value.first_run.side_effect = ApiException(status=400)
            with pytest.raises(GarmApiError):
                client.first_run("admin", "pass", "email@example.com", "Admin")


# ---------------------------------------------------------------------------
# GarmApiClient.login
# ---------------------------------------------------------------------------


def test_login_returns_token():
    """login returns the JWT token string from a successful response."""
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
    """login raises GarmApiError when the response token is absent or empty."""
    client = GarmApiClient(BASE_URL)
    mock_result = MagicMock()
    mock_result.token = token_value
    with _stub_api_client(client):
        with patch("garm_api.LoginApi") as MockApi:
            MockApi.return_value.login.return_value = mock_result
            with pytest.raises(error_type, match="token"):
                client.login("admin", "password")


def test_login_raises_on_api_error():
    """login raises GarmApiError when the API returns an error status."""
    client = GarmApiClient(BASE_URL)
    with _stub_api_client(client):
        with patch("garm_api.LoginApi") as MockApi:
            MockApi.return_value.login.side_effect = ApiException(status=401, reason="Unauthorized")
            with pytest.raises(GarmApiError):
                client.login("admin", "wrong")


# ---------------------------------------------------------------------------
# GarmAuthenticatedClient.list_providers
# ---------------------------------------------------------------------------


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
    """list_providers returns the correct provider names, or [] when the API returns None."""
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


# ---------------------------------------------------------------------------
# GarmAuthenticatedClient.list_scalesets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "api_response, expected_names",
    [
        ([("scaleset-a", 1), ("scaleset-b", 2)], ["scaleset-a", "scaleset-b"]),
        (None, []),
    ],
    ids=["two-scalesets", "none-response"],
)
def test_list_scalesets(api_response, expected_names):
    """list_scalesets returns the correct scaleset names, or [] when the API returns None."""
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


# ---------------------------------------------------------------------------
# GarmAuthenticatedClient.find_org_id / find_repo_id
# ---------------------------------------------------------------------------


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
    """find_org_id returns the UUID when the org is registered, else None."""
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
    """find_repo_id returns the UUID when the repo is registered, else None."""
    client = GarmAuthenticatedClient(BASE_URL, "token")
    mocks = []
    for i, name in enumerate(registered):
        m = MagicMock()
        m.name = name
        m.id = f"repo-uuid-{123 + i}" if name == target else f"other-uuid-{i}"
        mocks.append(m)
    with _stub_api_client(client):
        with patch("garm_api.RepositoriesApi") as MockApi:
            MockApi.return_value.list_repos.return_value = mocks
            result = client.find_repo_id(target)
    assert result == expected


# ---------------------------------------------------------------------------
# GarmAuthenticatedClient.delete_scaleset
# ---------------------------------------------------------------------------


def test_delete_scaleset_succeeds():
    """delete_scaleset completes without error and passes the correct scaleset_id."""
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.ScalesetsApi") as MockApi:
            client.delete_scaleset(42)
    MockApi.return_value.delete_scale_set.assert_called_once_with(
        scaleset_id="42", _request_timeout=30
    )


def test_delete_scaleset_raises_on_api_error():
    """delete_scaleset raises GarmApiError when the API returns an error status."""
    client = GarmAuthenticatedClient(BASE_URL, "token")
    with _stub_api_client(client):
        with patch("garm_api.ScalesetsApi") as MockApi:
            MockApi.return_value.delete_scale_set.side_effect = ApiException(status=404)
            with pytest.raises(GarmApiError):
                client.delete_scaleset(99)
