# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import hashlib
import hmac
import json
import time

import jubilant
import requests

APP_PORT = 8080


def create_flavor(
    juju: jubilant.Juju, planner_app: str, flavor_name: str
) -> requests.Response:
    """Create a flavor in the planner app."""
    status = juju.status()
    planner_ip = status.apps[planner_app].units[planner_app + "/0"].address

    return requests.post(
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


def get_flavor_pressure(
    juju: jubilant.Juju, planner_app: str, flavor_name: str
) -> dict:
    """Get the current pressure for a flavor."""
    status = juju.status()
    planner_ip = status.apps[planner_app].units[planner_app + "/0"].address

    response = requests.get(
        f"http://{planner_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}/pressure"
    )
    response.raise_for_status()
    return response.json()


def get_webhook_secret(juju: jubilant.Juju) -> str:
    """Retrieve the webhook secret from Juju secrets."""
    secrets = juju.list_secrets()
    webhook_secret_id = None

    for secret in secrets:
        if secret.get("label") == "webhook":
            webhook_secret_id = secret["id"]
            break

    if webhook_secret_id:
        secret_content = juju.show_secret(webhook_secret_id)
        return secret_content.get("value", "fake-secret")

    return "fake-secret"


def send_webhook(
    juju: jubilant.Juju,
    webhook_gateway_app: str,
    webhook_payload: dict,
    webhook_secret: str,
) -> requests.Response:
    """Send a webhook to the webhook gateway app."""
    status = juju.status()
    webhook_gateway_ip = (
        status.apps[webhook_gateway_app].units[webhook_gateway_app + "/0"].address
    )

    # Serialize payload and compute HMAC signature
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")

    # Compute HMAC-SHA256 signature
    signature = hmac.new(
        webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()

    return requests.post(
        f"http://{webhook_gateway_ip}:{APP_PORT}/webhook",
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
            "X-GitHub-Event": "workflow_job",
            "X-GitHub-Delivery": "12345678-1234-1234-1234-123456789012",
        },
    )


def test_webhook_gateway_and_planner_integration(
    juju: jubilant.Juju,
    planner_with_integrations: str,
    webhook_gateway_with_rabbitmq: str,
):
    """
    arrange: Both planner and webhook gateway deployed with postgresql and rabbitmq.
    act: Send a webhook to webhook gateway and check planner pressure.
    assert: Verify that the webhook is consumed and planner pressure updates.
    """
    planner_app = planner_with_integrations
    webhook_gateway_app = webhook_gateway_with_rabbitmq
    flavor_name = "test-flavor"

    # Create a flavor in planner
    create_flavor_response = create_flavor(juju, planner_app, flavor_name)
    assert create_flavor_response.status_code == requests.status_codes.codes.CREATED

    # Verify initial pressure is 0
    initial_pressure = get_flavor_pressure(juju, planner_app, flavor_name)
    assert initial_pressure[flavor_name] == 0

    # Prepare and send webhook
    webhook_payload = {
        "action": "queued",
        "workflow_job": {
            "id": 12345,
            "labels": ["self-hosted", "linux", "x64"],
            "status": "queued",
            "created_at": "2025-01-01T00:00:00Z",
        },
    }

    webhook_secret = get_webhook_secret(juju)
    webhook_response = send_webhook(
        juju, webhook_gateway_app, webhook_payload, webhook_secret
    )
    assert webhook_response.status_code == requests.status_codes.codes.OK

    # Wait for message processing
    time.sleep(5)

    # Verify pressure increased
    final_pressure = get_flavor_pressure(juju, planner_app, flavor_name)
    assert final_pressure[flavor_name] >= 1, (
        f"Expected pressure to increase after webhook consumption. "
        f"Initial: {initial_pressure[flavor_name]}, Final: {final_pressure[flavor_name]}"
    )
