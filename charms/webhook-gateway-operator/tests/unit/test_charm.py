# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GithubRunnerWebhookGatewayCharm environment generation."""

from unittest.mock import Mock, PropertyMock, patch

from charm import GithubRunnerWebhookGatewayCharm


def _call_gen_environment(config: dict, base_env: dict | None = None) -> dict[str, str]:
    """Create a charm with config and return gen_environment() output."""
    charm = GithubRunnerWebhookGatewayCharm.__new__(GithubRunnerWebhookGatewayCharm)

    # Two distinct mocks: first for original_app (closure captures its gen_environment),
    # second for the returned app (gets patched gen_environment).
    original_mock = Mock()
    original_mock.gen_environment.return_value = base_env if base_env else {}
    returned_mock = Mock()

    with (
        patch.object(type(charm), "config", new_callable=PropertyMock, return_value=config),
        patch(
            "paas_charm.go.Charm._create_app",
            side_effect=[original_mock, returned_mock],
        ),
    ):
        app = charm._create_app()
        return app.gen_environment()


def test_gen_environment_sets_otel_metrics():
    """arrange: A charm with metrics-port configured.

    act: Call gen_environment.
    assert: OTEL Prometheus exporter env vars are set.
    """
    env = _call_gen_environment({"metrics-port": 9464})

    assert env["OTEL_METRICS_EXPORTER"] == "prometheus"
    assert env["OTEL_EXPORTER_PROMETHEUS_HOST"] == "0.0.0.0"
    assert env["OTEL_EXPORTER_PROMETHEUS_PORT"] == "9464"
    assert env["OTEL_LOGS_EXPORTER"] == "console"


def test_gen_environment_sets_traces_endpoint():
    """arrange: A charm with OTEL endpoint set in base environment.

    act: Call gen_environment.
    assert: Traces endpoint is derived and OTLP endpoint is removed.
    """
    env = _call_gen_environment(
        {"metrics-port": 9464},
        base_env={"OTEL_EXPORTER_OTLP_ENDPOINT": "http://tempo:4318"},
    )

    assert env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] == "http://tempo:4318/v1/traces"
    assert env["OTEL_TRACES_EXPORTER"] == "otlp"
    assert env["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] == "http/protobuf"
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in env


def test_gen_environment_github_path_org_only():
    """arrange: A charm with github-path set to an organisation only.

    act: Call gen_environment.
    assert: APP_WEBHOOK_GITHUB_ORG is set; APP_WEBHOOK_GITHUB_REPO is absent.
    """
    env = _call_gen_environment({"metrics-port": 9464, "github-path": "canonical"})

    assert env["APP_WEBHOOK_GITHUB_ORG"] == "canonical"
    assert "APP_WEBHOOK_GITHUB_REPO" not in env


def test_gen_environment_github_path_org_and_repo():
    """arrange: A charm with github-path set to org/repo.

    act: Call gen_environment.
    assert: Both APP_WEBHOOK_GITHUB_ORG and APP_WEBHOOK_GITHUB_REPO are set.
    """
    env = _call_gen_environment(
        {"metrics-port": 9464, "github-path": "canonical/github-runner-operators"}
    )

    assert env["APP_WEBHOOK_GITHUB_ORG"] == "canonical"
    assert env["APP_WEBHOOK_GITHUB_REPO"] == "github-runner-operators"


def test_gen_environment_webhook_id():
    """arrange: A charm with webhook-id configured.

    act: Call gen_environment.
    assert: APP_WEBHOOK_ID is set.
    """
    env = _call_gen_environment({"metrics-port": 9464, "webhook-id": 456789})

    assert env["APP_WEBHOOK_ID"] == "456789"


def test_gen_environment_redelivery_interval():
    """arrange: A charm with redelivery-interval configured.

    act: Call gen_environment.
    assert: APP_REDELIVERY_INTERVAL_SECONDS is set.
    """
    env = _call_gen_environment({"metrics-port": 9464, "redelivery-interval": 300})

    assert env["APP_REDELIVERY_INTERVAL_SECONDS"] == "300"


def test_gen_environment_github_app_client_id():
    """arrange: A charm with github-app-client-id configured.

    act: Call gen_environment.
    assert: APP_GITHUB_APP_CLIENT_ID is set.
    """
    env = _call_gen_environment({"metrics-port": 9464, "github-app-client-id": "Iv1.abc123"})

    assert env["APP_GITHUB_APP_CLIENT_ID"] == "Iv1.abc123"


def test_gen_environment_github_app_installation_id():
    """arrange: A charm with github-app-installation-id configured.

    act: Call gen_environment.
    assert: APP_GITHUB_APP_INSTALLATION_ID is set.
    """
    env = _call_gen_environment({"metrics-port": 9464, "github-app-installation-id": 12345})

    assert env["APP_GITHUB_APP_INSTALLATION_ID"] == "12345"


def test_gen_environment_no_redelivery_config():
    """arrange: A charm with no redelivery-related config set.

    act: Call gen_environment.
    assert: No redelivery env vars are present.
    """
    env = _call_gen_environment({"metrics-port": 9464})

    assert "APP_WEBHOOK_GITHUB_ORG" not in env
    assert "APP_WEBHOOK_GITHUB_REPO" not in env
    assert "APP_WEBHOOK_ID" not in env
    assert "APP_REDELIVERY_INTERVAL_SECONDS" not in env
    assert "APP_GITHUB_APP_CLIENT_ID" not in env
    assert "APP_GITHUB_APP_INSTALLATION_ID" not in env


def test_gen_environment_full_redelivery_config():
    """arrange: A charm with all redelivery config options set.

    act: Call gen_environment.
    assert: All redelivery env vars are present with correct values.
    """
    env = _call_gen_environment(
        {
            "metrics-port": 9464,
            "github-path": "canonical/github-runner-operators",
            "webhook-id": 123456,
            "redelivery-interval": 900,
            "github-app-client-id": "Iv1.xyz",
            "github-app-installation-id": 99999,
        }
    )

    assert env["APP_WEBHOOK_GITHUB_ORG"] == "canonical"
    assert env["APP_WEBHOOK_GITHUB_REPO"] == "github-runner-operators"
    assert env["APP_WEBHOOK_ID"] == "123456"
    assert env["APP_REDELIVERY_INTERVAL_SECONDS"] == "900"
    assert env["APP_GITHUB_APP_CLIENT_ID"] == "Iv1.xyz"
    assert env["APP_GITHUB_APP_INSTALLATION_ID"] == "99999"
