# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GARM REST API client."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from garm_api import GarmApiError, GarmClient


def _make_response(body):
    """Build a mock urllib response context manager."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(body).encode()
    return mock_resp


def _make_http_error(status: int, body: str = "error"):
    return HTTPError(
        url="http://localhost:9997/api/v1/test",
        code=status,
        msg=body,
        hdrs=None,
        fp=BytesIO(body.encode()),
    )


def test_list_providers_returns_parsed_list():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([{"name": "openstack", "id": "abc"}])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_providers()
    assert result == [{"name": "openstack", "id": "abc"}]


def test_list_providers_returns_empty_on_null_body():
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""
        mock_open.return_value = mock_resp
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_providers()
    assert result == []


def test_list_credentials_returns_parsed_list():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([{"name": "github-app-12345"}])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_credentials()
    assert result == [{"name": "github-app-12345"}]


def test_list_scalesets_returns_parsed_list():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([{"id": "uuid-1", "name": "my-ss"}])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_scalesets()
    assert result == [{"id": "uuid-1", "name": "my-ss"}]


def test_create_scaleset_posts_and_returns_dict():
    expected = {"id": "new-uuid", "name": "my-ss"}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(expected)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.create_scaleset({"name": "my-ss"})
    assert result == expected


def test_update_scaleset_puts_and_returns_dict():
    expected = {"id": "uuid-1", "name": "my-ss", "flavor": "m1.xlarge"}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(expected)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.update_scaleset("uuid-1", {"flavor": "m1.xlarge"})
    assert result == expected


def test_delete_scaleset_makes_delete_request():
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""
        mock_open.return_value = mock_resp
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.delete_scaleset("uuid-1")
    call_args = mock_open.call_args
    req = call_args[0][0]
    assert req.get_method() == "DELETE"
    assert "uuid-1" in req.full_url


def test_request_raises_garm_api_error_on_http_error():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = _make_http_error(500, "internal server error")
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        with pytest.raises(GarmApiError, match="500"):
            client.list_providers()


def test_request_raises_garm_api_error_on_url_error():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = URLError("connection refused")
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        with pytest.raises(GarmApiError, match="connection refused"):
            client.list_providers()


def test_first_run_ignores_409():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = _make_http_error(409, "already initialized")
        client = GarmClient("http://localhost:9997/api/v1")
        # Should not raise
        client.first_run("admin", "password", "admin@test.local", "Admin")


def test_first_run_raises_on_other_errors():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.side_effect = _make_http_error(500, "server error")
        client = GarmClient("http://localhost:9997/api/v1")
        with pytest.raises(GarmApiError):
            client.first_run("admin", "password", "admin@test.local", "Admin")


def test_login_returns_token():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({"token": "eyJhbGci.payload.sig"})
        client = GarmClient("http://localhost:9997/api/v1")
        token = client.login("admin", "password")
    assert token == "eyJhbGci.payload.sig"


def test_login_raises_when_token_missing():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({"token": ""})
        client = GarmClient("http://localhost:9997/api/v1")
        with pytest.raises(GarmApiError, match="token"):
            client.login("admin", "password")


def test_bearer_token_sent_in_auth_header():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "my-jwt"
        client.list_scalesets()
    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer my-jwt"


def test_configure_controller_sends_put():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({})
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.configure_controller(
            metadata_url="http://1.2.3.4:9997/api/v1/metadata",
            callback_url="http://1.2.3.4:9997/api/v1/callbacks",
            webhook_url="http://1.2.3.4:9997/webhooks",
        )
    req = mock_open.call_args[0][0]
    assert req.get_method() == "PUT"
    body = json.loads(req.data)
    assert body["metadata_url"] == "http://1.2.3.4:9997/api/v1/metadata"
