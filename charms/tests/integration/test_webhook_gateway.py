# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import jubilant
import pytest
import requests

APP_PORT = 8080
METRICS_PORT = 9464


@pytest.mark.usefixtures("webhook_gateway_with_rabbitmq")
def test_webhook_gateway_rabbitmq_integration(
    juju: jubilant.Juju,
    webhook_gateway_app: str,
):
    """
    arrange: The webhook gateway app and rabbitmq deployed and integrated with each other.
    act: Send a http request to the webhook gateway app.
    assert: Assert that the server responds with a status code of 200
    """

    status = juju.status()
    unit_ip = status.apps[webhook_gateway_app].units[webhook_gateway_app + "/0"].address
    response = requests.post(
        f"http://{unit_ip}:{APP_PORT}/webhook",
        data='{"message":"Hello, Alice!"}',
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=0aca2d7154cddad4f56f246cad61f1485df"
            "34b8056e10c4e4799494376fb3413",
            "X-GitHub-Event": "workflow_job",
            "X-GitHub-Delivery": "12345678-1234-1234-1234-123456789012",
        },
    )

    assert response.status_code == requests.status_codes.codes.OK


@pytest.mark.usefixtures("webhook_gateway_with_rabbitmq")
def test_webhook_gateway_prometheus_metrics(
    juju: jubilant.Juju,
    webhook_gateway_app: str,
):
    """
    arrange: The webhook gateway app is deployed.
    act: Get Prometheus metrics from the charm.
    assert: Assert that the server responds with a status code of 200
    """
    status = juju.status()
    unit_ip = status.apps[webhook_gateway_app].units[webhook_gateway_app + "/0"].address
    response = requests.get(f"http://{unit_ip}:{METRICS_PORT}/metrics")

    assert response.status_code == requests.status_codes.codes.OK
