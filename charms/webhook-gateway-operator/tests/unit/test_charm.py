# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import PropertyMock, patch

import pytest

from charm import GithubRunnerWebhookGatewayCharm


@pytest.fixture
def charm():
    """Create a charm instance with mocked config property."""
    with patch.object(GithubRunnerWebhookGatewayCharm, "__init__", lambda self, *a: None):
        c = object.__new__(GithubRunnerWebhookGatewayCharm)
        c._config = {}
        return c


def _set_config(charm, config):
    """Patch the config property to return the given dict."""
    return patch.object(type(charm), "config", new_callable=PropertyMock, return_value=config)


class TestValidateRedeliveryConfig:
    """Tests for _validate_redelivery_config."""

    def test_disabled_when_no_redelivery_fields(self, charm):
        with _set_config(charm, {}):
            assert charm._validate_redelivery_config() is None

    @pytest.mark.parametrize(
        "partial_config, expected_missing",
        [
            pytest.param(
                {"github-path": "my-org"},
                [
                    "webhook-id",
                    "github-app-id",
                    "github-app-installation-id",
                    "github-app-private-key",
                ],
                id="only-github-path",
            ),
            pytest.param(
                {"webhook-id": 123},
                [
                    "github-path",
                    "github-app-id",
                    "github-app-installation-id",
                    "github-app-private-key",
                ],
                id="only-webhook-id",
            ),
            pytest.param(
                {"github-app-id": 789},
                [
                    "github-path",
                    "webhook-id",
                    "github-app-installation-id",
                    "github-app-private-key",
                ],
                id="only-app-id",
            ),
            pytest.param(
                {"github-path": "my-org", "webhook-id": 123},
                ["github-app-id", "github-app-installation-id", "github-app-private-key"],
                id="missing-all-auth",
            ),
            pytest.param(
                {
                    "github-path": "my-org",
                    "webhook-id": 123,
                    "github-app-id": 789,
                    "github-app-installation-id": 456,
                },
                ["github-app-private-key"],
                id="missing-private-key",
            ),
            pytest.param(
                {"github-path": "my-org", "webhook-id": 123, "github-app-private-key": "secret:x"},
                ["github-app-id", "github-app-installation-id"],
                id="missing-app-ids",
            ),
        ],
    )
    def test_blocked_when_fields_missing(self, charm, partial_config, expected_missing):
        with _set_config(charm, partial_config):
            result = charm._validate_redelivery_config()
            assert result is not None
            for field in expected_missing:
                assert field in result

    def test_valid_when_all_fields_present(self, charm):
        config = {
            "github-path": "my-org",
            "webhook-id": 123,
            "github-app-id": 789,
            "github-app-installation-id": 456,
            "github-app-private-key": "secret:abc",
        }
        with _set_config(charm, config):
            assert charm._validate_redelivery_config() is None

    def test_valid_with_repo_path(self, charm):
        config = {
            "github-path": "my-org/my-repo",
            "webhook-id": 123,
            "github-app-id": 789,
            "github-app-installation-id": 456,
            "github-app-private-key": "secret:abc",
        }
        with _set_config(charm, config):
            assert charm._validate_redelivery_config() is None

    @pytest.mark.parametrize(
        "field, value",
        [
            pytest.param("webhook-id", -1, id="negative-webhook-id"),
            pytest.param("github-app-id", -5, id="negative-app-id"),
            pytest.param("github-app-installation-id", -10, id="negative-installation-id"),
            pytest.param("redelivery-interval", 0, id="zero-redelivery-interval"),
            pytest.param("redelivery-interval", -60, id="negative-redelivery-interval"),
        ],
    )
    def test_blocked_when_int_field_not_positive(self, charm, field, value):
        config = {
            "github-path": "my-org",
            "webhook-id": 123,
            "github-app-id": 789,
            "github-app-installation-id": 456,
            "github-app-private-key": "secret:abc",
            "redelivery-interval": 600,
            field: value,
        }
        with _set_config(charm, config):
            result = charm._validate_redelivery_config()
            assert result is not None
            assert field in result
            assert "positive integers" in result

    @pytest.mark.parametrize(
        "field, value",
        [
            pytest.param("webhook-id", "abc", id="string-webhook-id"),
            pytest.param("github-app-id", 3.14, id="float-app-id"),
            pytest.param(
                "github-app-installation-id",
                "not-a-number",
                id="string-installation-id",
            ),
            pytest.param("redelivery-interval", "fast", id="string-redelivery-interval"),
        ],
    )
    def test_blocked_when_int_field_has_wrong_type(self, charm, field, value):
        config = {
            "github-path": "my-org",
            "webhook-id": 123,
            "github-app-id": 789,
            "github-app-installation-id": 456,
            "github-app-private-key": "secret:abc",
            "redelivery-interval": 600,
            field: value,
        }
        with _set_config(charm, config):
            result = charm._validate_redelivery_config()
            assert result is not None
            assert field in result
            assert "positive integers" in result
