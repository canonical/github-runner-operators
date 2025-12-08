# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import hashlib
import hmac
import json
import time

import jubilant
import pytest
import requests

APP_PORT = 8080


@pytest.mark.usefixtures("planner_and_webhook_gateway_ready")
def test_webhook_gateway_and_planner_integration(
    juju: jubilant.Juju,
    planner_app: str,
    webhook_gateway_app: str,
):
    """
    arrange: Both planner and webhook gateway deployed with postgresql and rabbitmq.
    act: Send a webhook to webhook gateway and check planner pressure.
    assert: Verify that the webhook is consumed and planner pressure updates.
    """
    # First, create a flavor in planner
    status = juju.status()
    planner_ip = status.apps[planner_app].units[planner_app + "/0"].address

    flavor_name = "test-flavor"
    create_flavor_response = requests.post(
        f"http://{planner_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        json={
            "platform": "github",
            "labels": ["self-hosted", "linux", "x64"],
            "priority": 100,
            "minimum_pressure": 0,
        },
        headers={
            "Content-Type": "application/json",
        },
    )

    assert create_flavor_response.status_code == requests.status_codes.codes.CREATED

    # Verify initial pressure is 0
    initial_pressure_response = requests.get(
        f"http://{planner_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}/pressure"
    )
    assert initial_pressure_response.status_code == requests.status_codes.codes.OK
    initial_pressure = initial_pressure_response.json()
    assert initial_pressure[flavor_name] == 0

    # Send a workflow_job webhook to webhook gateway
    webhook_gateway_ip = (
        status.apps[webhook_gateway_app].units[webhook_gateway_app + "/0"].address
    )

    webhook_payload = {
        "action": "queued",
        "workflow_job": {
            "id": 12345,
            "labels": ["self-hosted", "linux", "x64"],
            "status": "queued",
            "created_at": "2025-01-01T00:00:00Z",
        },
    }

    # Serialize payload and compute HMAC signature
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")

    # Get the webhook secret from the juju secret
    secrets = juju.list_secrets()
    webhook_secret_id = None
    for secret in secrets:
        if secret.get("label") == "webhook":
            webhook_secret_id = secret["id"]
            break

    if webhook_secret_id:
        secret_content = juju.show_secret(webhook_secret_id)
        webhook_secret = secret_content.get("value", "fake-secret")
    else:
        webhook_secret = "fake-secret"

    # Compute HMAC-SHA256 signature
    signature = hmac.new(
        webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()

    webhook_response = requests.post(
        f"http://{webhook_gateway_ip}:{APP_PORT}/webhook",
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
            "X-GitHub-Event": "workflow_job",
            "X-GitHub-Delivery": "12345678-1234-1234-1234-123456789012",
        },
    )

    # Webhook should be accepted with valid signature
    assert webhook_response.status_code == requests.status_codes.codes.OK

    # Wait a bit for the message to be consumed and processed
    time.sleep(5)

    # Check planner pressure - it should have increased
    final_pressure_response = requests.get(
        f"http://{planner_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}/pressure"
    )
    assert final_pressure_response.status_code == requests.status_codes.codes.OK
    final_pressure = final_pressure_response.json()

    # Pressure should have increased by at least 1
    assert final_pressure[flavor_name] >= 1, (
        f"Expected pressure to increase after webhook consumption. "
        f"Initial: {initial_pressure[flavor_name]}, Final: {final_pressure[flavor_name]}"
    )
