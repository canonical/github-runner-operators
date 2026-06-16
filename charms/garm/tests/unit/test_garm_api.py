# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GARM REST API client."""

import base64
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


# ---------------------------------------------------------------------------
# Template API tests
# ---------------------------------------------------------------------------


def test_list_templates_returns_parsed_list():
    expected = [{"id": 1, "name": "my-template", "os_type": "linux", "forge_type": "github"}]
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(expected)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_templates()
    assert result == expected
    req = mock_open.call_args[0][0]
    assert req.get_method() == "GET"
    assert req.full_url == "http://localhost:9997/api/v1/templates"


def test_list_templates_returns_empty_on_null_body():
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""
        mock_open.return_value = mock_resp
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.list_templates()
    assert result == []


def test_list_templates_builds_query_params():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.list_templates(os_type="linux", forge_type="github", partial_name="runner")
    req = mock_open.call_args[0][0]
    assert "os_type=linux" in req.full_url
    assert "forge_type=github" in req.full_url
    assert "partial_name=runner" in req.full_url


def test_list_templates_omits_none_params():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response([])
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.list_templates(os_type="linux")
    req = mock_open.call_args[0][0]
    assert "os_type=linux" in req.full_url
    assert "forge_type" not in req.full_url
    assert "partial_name" not in req.full_url


def test_get_template_returns_parsed_dict():
    expected = {"id": 1, "name": "my-template", "data": "aGVsbG8="}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(expected)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.get_template(1)
    assert result == expected
    req = mock_open.call_args[0][0]
    assert req.get_method() == "GET"
    assert req.full_url.endswith("/templates/1")


def test_create_template_base64_encodes_data():
    raw = b"#!/bin/bash\necho hello"
    expected_b64 = base64.b64encode(raw).decode()
    created = {"id": 2, "name": "new-tmpl", "data": expected_b64}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(created)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.create_template(name="new-tmpl", data=raw)
    assert result == created
    req = mock_open.call_args[0][0]
    assert req.get_method() == "POST"
    assert req.full_url.endswith("/templates")
    body = json.loads(req.data)
    assert body["data"] == expected_b64
    assert body["name"] == "new-tmpl"
    assert body["os_type"] == "linux"
    assert body["forge_type"] == "github"
    assert body["description"] == ""


def test_create_template_accepts_custom_os_and_forge():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({"id": 3})
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.create_template(
            name="win-tmpl",
            data=b"data",
            os_type="windows",
            forge_type="gitea",
            description="A windows template",
        )
    body = json.loads(mock_open.call_args[0][0].data)
    assert body["os_type"] == "windows"
    assert body["forge_type"] == "gitea"
    assert body["description"] == "A windows template"


def test_update_template_base64_encodes_data():
    raw = b"new content"
    expected_b64 = base64.b64encode(raw).decode()
    updated = {"id": 1, "data": expected_b64}
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(updated)
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.update_template(1, data=raw)
    assert result == updated
    req = mock_open.call_args[0][0]
    assert req.get_method() == "PUT"
    assert req.full_url.endswith("/templates/1")
    body = json.loads(req.data)
    assert body["data"] == expected_b64
    assert "name" not in body
    assert "description" not in body


def test_update_template_includes_optional_fields_when_set():
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response({"id": 1})
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        client.update_template(1, data=b"x", name="updated", description="new desc")
    body = json.loads(mock_open.call_args[0][0].data)
    assert body["name"] == "updated"
    assert body["description"] == "new desc"
    assert body["data"] == base64.b64encode(b"x").decode()


def test_delete_template_makes_delete_request():
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b""
        mock_open.return_value = mock_resp
        client = GarmClient("http://localhost:9997/api/v1")
        client.token = "test-token"
        result = client.delete_template(5)
    assert result is None
    req = mock_open.call_args[0][0]
    assert req.get_method() == "DELETE"
    assert req.full_url.endswith("/templates/5")
