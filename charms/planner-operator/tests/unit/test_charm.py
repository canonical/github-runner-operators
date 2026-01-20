# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GithubRunnerPlannerCharm.

Note: These tests use mocking rather than ops-scenario because:
1. The go-framework extension metadata (peers, containers, config) is injected at
   charmcraft pack time and would need to be manually defined for ops-scenario
2. Testing only the is_ready() override requires mocking super().is_ready() either way
3. For this focused validation logic, direct mocking is pragmatic
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from ops import BlockedStatus

from charm import ADMIN_TOKEN_PATTERN, GithubRunnerPlannerCharm


@patch.object(GithubRunnerPlannerCharm, "config", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "model", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "unit", new_callable=PropertyMock)
@patch("paas_charm.go.Charm.is_ready", return_value=True)
def test_valid_token_calls_super(mock_super_is_ready, mock_unit, mock_model, mock_config):
    """
    arrange: Charm with valid admin-token secret configured.
    act: Call is_ready() on the charm.
    assert: Returns True and calls parent is_ready().
    """
    mock_config.return_value.get.return_value = "secret:abc123"
    mock_secret = MagicMock()
    mock_secret.get_content.return_value = {"value": "planner_v0_abcdefghij1234567890"}
    mock_model.return_value.get_secret.return_value = mock_secret
    mock_unit.return_value = MagicMock()

    charm = object.__new__(GithubRunnerPlannerCharm)

    result = charm.is_ready()

    assert result is True
    mock_super_is_ready.assert_called_once()
    mock_model.return_value.get_secret.assert_called_once_with(id="secret:abc123")


@patch.object(GithubRunnerPlannerCharm, "config", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "unit", new_callable=PropertyMock)
@patch("paas_charm.go.Charm.is_ready", return_value=True)
def test_no_token_configured_calls_super(mock_super_is_ready, mock_unit, mock_config):
    """
    arrange: Charm with no admin-token configured.
    act: Call is_ready() on the charm.
    assert: Returns True and defers to parent is_ready().
    """
    mock_config.return_value.get.return_value = None
    mock_unit.return_value = MagicMock()

    charm = object.__new__(GithubRunnerPlannerCharm)

    result = charm.is_ready()

    assert result is True
    mock_super_is_ready.assert_called_once()


@pytest.mark.parametrize(
    "invalid_token",
    [
        pytest.param("", id="empty_string"),
        pytest.param("invalid", id="no_prefix"),
        pytest.param("planner_v0_short", id="too_short"),
        pytest.param("planner_v0_waytoolongtoken12345678", id="too_long"),
        pytest.param("planner_v1_abcdefghij1234567890", id="wrong_version"),
        pytest.param("planner_v0_abcdefghij123456789!", id="invalid_char"),
    ],
)
@patch.object(GithubRunnerPlannerCharm, "config", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "model", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "unit", new_callable=PropertyMock)
@patch("paas_charm.go.Charm.is_ready", return_value=True)
def test_invalid_token_blocks(
    mock_super_is_ready, mock_unit, mock_model, mock_config, invalid_token
):
    """
    arrange: Charm with invalid admin-token secret.
    act: Call is_ready() on the charm.
    assert: Returns False and sets BlockedStatus with validation error.
    """
    mock_config.return_value.get.return_value = "secret:abc123"
    mock_secret = MagicMock()
    mock_secret.get_content.return_value = {"value": invalid_token}
    mock_model.return_value.get_secret.return_value = mock_secret
    mock_unit_instance = MagicMock()
    mock_unit.return_value = mock_unit_instance

    charm = object.__new__(GithubRunnerPlannerCharm)

    result = charm.is_ready()

    assert result is False
    assert isinstance(mock_unit_instance.status, BlockedStatus)
    assert "invalid admin-token format" in mock_unit_instance.status.message
    mock_super_is_ready.assert_not_called()


@patch.object(GithubRunnerPlannerCharm, "config", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "model", new_callable=PropertyMock)
@patch.object(GithubRunnerPlannerCharm, "unit", new_callable=PropertyMock)
@patch("paas_charm.go.Charm.is_ready", return_value=True)
def test_secret_read_failure_calls_super(mock_super_is_ready, mock_unit, mock_model, mock_config):
    """
    arrange: Charm with admin-token secret that fails to read.
    act: Call is_ready() on the charm.
    assert: Logs warning and defers to parent is_ready().
    """
    mock_config.return_value.get.return_value = "secret:abc123"
    mock_model.return_value.get_secret.side_effect = Exception("Secret not found")
    mock_unit.return_value = MagicMock()

    charm = object.__new__(GithubRunnerPlannerCharm)

    result = charm.is_ready()

    assert result is True
    mock_super_is_ready.assert_called_once()


@pytest.mark.parametrize(
    "valid_token",
    [
        "planner_v0_abcdefghij1234567890",
        "planner_v0_ABCDEFGHIJ1234567890",
        "planner_v0_abc-def_ghi-123_4567",
        "planner_v0_01234567890123456789",
    ],
)
def test_valid_token_patterns(valid_token):
    """
    arrange: Valid admin token format.
    act: Match against ADMIN_TOKEN_PATTERN.
    assert: Pattern matches the token.
    """
    assert ADMIN_TOKEN_PATTERN.match(valid_token)


@pytest.mark.parametrize(
    "invalid_token",
    [
        "",
        "planner_v0_",
        "planner_v0_short",
        "planner_v0_waytoolongtoken12345678",
        "planner_v1_abcdefghij1234567890",
        "other_v0_abcdefghij1234567890",
        "planner_v0_abcdefghij123456789!",
    ],
)
def test_invalid_token_patterns(invalid_token):
    """
    arrange: Invalid admin token format.
    act: Match against ADMIN_TOKEN_PATTERN.
    assert: Pattern does not match the token.
    """
    assert not ADMIN_TOKEN_PATTERN.match(invalid_token)
