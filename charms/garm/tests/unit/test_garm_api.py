# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the GarmApiClient wrapper."""

from unittest.mock import MagicMock, patch

import pytest
import urllib3.exceptions

from garm_api import GarmApiClient, GarmApiError, GarmConnectionError
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


def test_is_initialized_raises_on_connection_error(client):
    """
    arrange: ControllerInfoApi.controller_info raises urllib3 HTTPError.
    act: Call client.is_initialized().
    assert: Raises GarmConnectionError (subclass of GarmApiError) wrapping the error.
    """
    with patch("garm_api.ControllerInfoApi") as mock_cls:
        mock_cls.return_value.controller_info.side_effect = urllib3.exceptions.HTTPError("refused")
        with pytest.raises(GarmConnectionError, match="connection error"):
            client.is_initialized()


def test_first_run_raises_on_connection_error(client):
    """
    arrange: FirstRunApi.first_run raises urllib3 HTTPError.
    act: Call client.first_run().
    assert: Raises GarmConnectionError (subclass of GarmApiError) wrapping the error.
    """
    with patch("garm_api.FirstRunApi") as mock_cls:
        mock_cls.return_value.first_run.side_effect = urllib3.exceptions.HTTPError("refused")
        with pytest.raises(GarmConnectionError, match="connection error"):
            client.first_run("admin", "Password-123!", "admin@test.local", "Admin User")


def test_wait_for_ready_returns_when_initialized(client):
    """
    arrange: is_initialized() returns True on first call.
    act: Call client.wait_for_ready().
    assert: Returns without raising.
    """
    with patch.object(client, "is_initialized", return_value=True):
        client.wait_for_ready()


def test_wait_for_ready_returns_when_not_yet_initialized(client):
    """
    arrange: is_initialized() returns False (409 — server up, awaiting first-run).
    act: Call client.wait_for_ready().
    assert: Returns without raising (False means HTTP API is up).
    """
    with patch.object(client, "is_initialized", return_value=False):
        client.wait_for_ready()


def test_wait_for_ready_retries_on_connection_error_then_succeeds(client):
    """
    arrange: is_initialized() raises GarmConnectionError once, then returns True.
    act: Call client.wait_for_ready().
    assert: Returns without raising after the retry.
    """
    with (
        patch.object(
            client,
            "is_initialized",
            side_effect=[GarmConnectionError("refused"), True],
        ),
        patch("garm_api.time.sleep"),
    ):
        client.wait_for_ready()


def test_wait_for_ready_raises_after_timeout(client):
    """
    arrange: is_initialized() always raises GarmConnectionError; monotonic clock advances
             past the timeout on the second call.
    act: Call client.wait_for_ready(timeout=5).
    assert: Raises GarmConnectionError mentioning the timeout duration.
    """
    monotonic_values = iter([0.0, 0.0, 10.0])  # deadline=5, first check passes, second exceeds

    with (
        patch.object(client, "is_initialized", side_effect=GarmConnectionError("refused")),
        patch("garm_api.time.monotonic", side_effect=monotonic_values),
        patch("garm_api.time.sleep"),
    ):
        with pytest.raises(GarmConnectionError, match="5s"):
            client.wait_for_ready(timeout=5)


def test_wait_for_ready_propagates_non_connection_api_error_immediately(client):
    """
    arrange: is_initialized() raises GarmApiError (unexpected HTTP status, not a connection error).
    act: Call client.wait_for_ready().
    assert: GarmApiError propagates immediately without retrying.
    """
    with (
        patch.object(client, "is_initialized", side_effect=GarmApiError("unexpected 500")),
        patch("garm_api.time.sleep") as mock_sleep,
    ):
        with pytest.raises(GarmApiError, match="unexpected 500"):
            client.wait_for_ready()

    mock_sleep.assert_not_called()
