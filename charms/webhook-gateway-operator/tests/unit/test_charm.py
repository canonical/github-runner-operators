# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import ops
import ops.testing
import pytest
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


class TestCharmBlockedStatus:
    """Tests verifying the charm enters BlockedStatus on invalid redelivery config."""

    def test_blocked_on_incomplete_redelivery_config(self):
        ctx = ops.testing.Context(GithubRunnerWebhookGatewayCharm)
        webhook_secret = ops.testing.Secret(tracked_content={"value": "s3cr3t"})
        state = ops.testing.State(
            config={"github-path": "my-org", "webhook-secret": webhook_secret.id},
            containers=[ops.testing.Container(name="app", can_connect=True)],
            secrets=[webhook_secret],
        )
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.BlockedStatus("Invalid redelivery config")

    def test_blocked_on_complete_but_invalid_redelivery_config(self):
        ctx = ops.testing.Context(GithubRunnerWebhookGatewayCharm)
        webhook_secret = ops.testing.Secret(tracked_content={"value": "s3cr3t"})
        app_private_key = ops.testing.Secret(tracked_content={"value": "pem-content"})
        state = ops.testing.State(
            config={
                "github-path": "my-org",
                "webhook-id": 123,
                "github-app-id": 789,
                "github-app-installation-id": 456,
                "github-app-private-key": app_private_key.id,
                "redelivery-interval": 0,
                "webhook-secret": webhook_secret.id,
            },
            containers=[ops.testing.Container(name="app", can_connect=True)],
            secrets=[webhook_secret, app_private_key],
        )
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ops.BlockedStatus("Invalid redelivery config")
