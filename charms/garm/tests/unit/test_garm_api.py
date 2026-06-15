# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GarmApiClient wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from garm_api import GarmApiClient, GarmApiError
from garm_client.exceptions import ApiException


@pytest.fixture(name="client")
def client_fixture():
    """Return a GarmApiClient pointed at a local test address."""
    return GarmApiClient("http://127.0.0.1:9997/api/v1")


def test_is_initialized_returns_true_when_controller_info_succeeds(client):
    """
    arrange: ControllerInfoApi.controller_info returns successfully.
    act: Call client.is_initialized().
    assert: Returns True.
    """
    with patch("garm_api.ControllerInfoApi") as mock_cls:
        mock_cls.return_value.controller_info.return_value = MagicMock()
        assert client.is_initialized() is True


def test_is_initialized_returns_false_on_409(client):
    """
    arrange: ControllerInfoApi.controller_info raises ApiException with status 409.
    act: Call client.is_initialized().
    assert: Returns False (GARM not yet initialised).
    """
    with patch("garm_api.ControllerInfoApi") as mock_cls:
        mock_cls.return_value.controller_info.side_effect = ApiException(status=409)
        assert client.is_initialized() is False


def test_is_initialized_raises_on_unexpected_status(client):
    """
    arrange: ControllerInfoApi.controller_info raises ApiException with status 500.
    act: Call client.is_initialized().
    assert: Raises GarmApiError with the status code in the message.
    """
    with patch("garm_api.ControllerInfoApi") as mock_cls:
        mock_cls.return_value.controller_info.side_effect = ApiException(status=500)
        with pytest.raises(GarmApiError, match="500"):
            client.is_initialized()


def test_first_run_calls_api_with_correct_params(client):
    """
    arrange: FirstRunApi.first_run returns successfully.
    act: Call client.first_run() with known parameters.
    assert: The API is called with a NewUserParams body matching those parameters.
    """
    with patch("garm_api.FirstRunApi") as mock_cls:
        mock_cls.return_value.first_run.return_value = MagicMock()
        client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")
    body = mock_cls.return_value.first_run.call_args.kwargs["body"]
    assert body.username == "admin"
    assert body.password == "Password-123!"
    assert body.email == "admin@test.local"
    assert body.full_name == "Admin User"


def test_first_run_raises_on_api_error(client):
    """
    arrange: FirstRunApi.first_run raises ApiException with status 400.
    act: Call client.first_run().
    assert: Raises GarmApiError with the status code in the message.
    """
    with patch("garm_api.FirstRunApi") as mock_cls:
        mock_cls.return_value.first_run.side_effect = ApiException(status=400)
        with pytest.raises(GarmApiError, match="400"):
            client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")
