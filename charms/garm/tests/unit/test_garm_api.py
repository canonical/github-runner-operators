# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GarmApiClient wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from garm_api import GarmApiClient, GarmApiError
from garm_client.exceptions import ApiException


@pytest.fixture()
def client():
    return GarmApiClient("http://127.0.0.1:9997/api/v1")


class TestIsInitialized:
    def test_returns_true_when_controller_info_succeeds(self, client):
        with patch("garm_api.ControllerInfoApi") as mock_cls:
            mock_cls.return_value.controller_info.return_value = MagicMock()
            assert client.is_initialized() is True

    def test_returns_false_on_409(self, client):
        exc = ApiException(status=409)
        with patch("garm_api.ControllerInfoApi") as mock_cls:
            mock_cls.return_value.controller_info.side_effect = exc
            assert client.is_initialized() is False

    def test_raises_garm_api_error_on_unexpected_status(self, client):
        exc = ApiException(status=500)
        with patch("garm_api.ControllerInfoApi") as mock_cls:
            mock_cls.return_value.controller_info.side_effect = exc
            with pytest.raises(GarmApiError):
                client.is_initialized()


class TestLogin:
    def test_returns_jwt_token(self, client):
        mock_response = MagicMock()
        mock_response.token = "test-jwt"
        with patch("garm_api.LoginApi") as mock_cls:
            mock_cls.return_value.login.return_value = mock_response
            token = client.login("admin", "password")
        assert token == "test-jwt"

    def test_raises_garm_api_error_on_failure(self, client):
        exc = ApiException(status=401)
        with patch("garm_api.LoginApi") as mock_cls:
            mock_cls.return_value.login.side_effect = exc
            with pytest.raises(GarmApiError):
                client.login("admin", "wrong-password")


class TestFirstRun:
    def test_calls_api_with_correct_params(self, client):
        with patch("garm_api.FirstRunApi") as mock_cls:
            mock_cls.return_value.first_run.return_value = MagicMock()
            client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")
        call_kwargs = mock_cls.return_value.first_run.call_args
        body = call_kwargs.kwargs["body"]
        assert body.username == "admin"
        assert body.password == "Password-123!"
        assert body.email == "admin@test.local"
        assert body.full_name == "Admin User"

    def test_raises_garm_api_error_on_failure(self, client):
        exc = ApiException(status=400)
        with patch("garm_api.FirstRunApi") as mock_cls:
            mock_cls.return_value.first_run.side_effect = exc
            with pytest.raises(GarmApiError):
                client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")
