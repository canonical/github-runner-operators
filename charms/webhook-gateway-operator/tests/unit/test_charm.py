# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from paas_charm.exceptions import CharmConfigInvalidError
from pydantic import ValidationError

from charm import GithubRunnerWebhookGatewayCharm, WebhookGatewayConfig

_VALID_REDELIVERY_CONFIG = {
    "github-path": "my-org",
    "webhook-id": 123,
    "github-app-id": 789,
    "github-app-installation-id": 456,
    "github-app-private-key": "secret:abc",
}


class TestWebhookGatewayConfig:
    """Tests for WebhookGatewayConfig pydantic validation."""

    def test_valid_when_no_redelivery_fields(self):
        WebhookGatewayConfig.model_validate({})

    def test_valid_when_all_fields_present(self):
        WebhookGatewayConfig.model_validate(_VALID_REDELIVERY_CONFIG)

    def test_valid_with_repo_path(self):
        config = {**_VALID_REDELIVERY_CONFIG, "github-path": "my-org/my-repo"}
        WebhookGatewayConfig.model_validate(config)

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
                [
                    "github-app-id",
                    "github-app-installation-id",
                    "github-app-private-key",
                ],
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
                {
                    "github-path": "my-org",
                    "webhook-id": 123,
                    "github-app-private-key": "secret:x",
                },
                ["github-app-id", "github-app-installation-id"],
                id="missing-app-ids",
            ),
        ],
    )
    def test_blocked_when_fields_missing(self, partial_config, expected_missing):
        with pytest.raises(ValidationError) as exc_info:
            WebhookGatewayConfig.model_validate(partial_config)
        error_text = str(exc_info.value)
        for field in expected_missing:
            assert field in error_text

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
    def test_blocked_when_int_field_not_positive(self, field, value):
        config = {**_VALID_REDELIVERY_CONFIG, "redelivery-interval": 600, field: value}
        with pytest.raises(ValidationError):
            WebhookGatewayConfig.model_validate(config)

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
    def test_blocked_when_int_field_has_wrong_type(self, field, value):
        config = {**_VALID_REDELIVERY_CONFIG, "redelivery-interval": 600, field: value}
        with pytest.raises(ValidationError):
            WebhookGatewayConfig.model_validate(config)


_PATCH_CONFIG_GET = patch(
    "paas_charm.charm.config_get_with_secret",
    side_effect=lambda _charm, k: _charm.config.get(k),
)


class TestCharmBlockedStatus:
    """Tests verifying invalid config raises CharmConfigInvalidError (→ BlockedStatus)."""

    @_PATCH_CONFIG_GET
    def test_blocked_on_incomplete_redelivery_config(self, _mock_config_get):
        """get_framework_config raises CharmConfigInvalidError on partial redelivery config.

        paas_charm's restart() catches this and sets BlockedStatus.
        """
        charm = MagicMock()
        charm.framework_config_class = WebhookGatewayConfig
        charm.config = {"github-path": "my-org", "redelivery-interval": 600}

        with pytest.raises(CharmConfigInvalidError):
            GithubRunnerWebhookGatewayCharm.get_framework_config(charm)

    @_PATCH_CONFIG_GET
    def test_not_blocked_when_all_redelivery_fields_present(self, _mock_config_get):
        charm = MagicMock()
        charm.framework_config_class = WebhookGatewayConfig
        charm.config = {**_VALID_REDELIVERY_CONFIG, "redelivery-interval": 600}

        result = GithubRunnerWebhookGatewayCharm.get_framework_config(charm)
        assert result.github_path == "my-org"
