# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import time
import jubilant
import pytest
import requests

APP_PORT = 8080
METRICS_PORT = 9464


@pytest.mark.usefixtures("planner_with_integrations")
def test_planner_postgresql_integration(
    juju: jubilant.Juju,
    planner_app: str,
    user_token: str,
):
    """
    arrange: The planner app and postgresql deployed and integrated with each other.
    act: Send a http request to the planner app.
    assert: Assert that the server responds with a status code of 200
    """

    status = juju.status()
    unit_ip = status.apps[planner_app].units[planner_app + "/0"].address
    response = requests.post(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/test-flavor",
        json={
            "platform": "github",
            "labels": ["self-hosted", "amd64"],
            "priority": 100,
            "minimum_pressure": 0,
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}",
        },
        timeout=30,
    )

    assert response.status_code == requests.status_codes.codes.created


@pytest.mark.usefixtures("planner_with_integrations")
def test_planner_prometheus_metrics(
    juju: jubilant.Juju,
    planner_app: str,
):
    """
    arrange: The planner app is deployed with required integrations.
    act: Get Prometheus metrics from the charm.
    assert: Assert that the server responds with a status code of 200
    """
    status = juju.status()
    unit_ip = status.apps[planner_app].units[planner_app + "/0"].address
    response = requests.get(f"http://{unit_ip}:{METRICS_PORT}/metrics", timeout=30)

    assert response.status_code == requests.status_codes.codes.OK


@pytest.mark.usefixtures("planner_with_integrations")
def test_planner_github_runner_integration(
    juju: jubilant.Juju,
    planner_app: str,
    any_charm_github_runner_app: str,
    user_token: str,
):
    """
    arrange: The planner app and any-charm app mocking github-runner is deployed.
    act: Integrate, verify relation data and managed flavor creation, then remove
         the relation and verify managed flavor cleanup.
    assert: The integration data contains the endpoint and auth token, the managed
            flavor is created on relation setup and deleted on relation removal.
    """
    status = juju.status()
    unit_ip = status.apps[planner_app].units[f"{planner_app}/0"].address
    github_runner_app = any_charm_github_runner_app
    flavor_name = "test-relation-flavor"

    juju.integrate(f"{planner_app}:planner", github_runner_app)
    juju.wait(
        lambda status: jubilant.all_active(status, planner_app),
        timeout=6 * 60,
        delay=10,
    )

    unit = f"{github_runner_app}/0"
    stdout = juju.cli("show-unit", unit, "--format=json")
    result = json.loads(stdout)
    for relation in result[unit]["relation-info"]:
        if relation["endpoint"] == "provide-github-runner-planner-v0":
            assert "http://" in relation["application-data"]["endpoint"]
            assert "secret://" in relation["application-data"]["token"]
            break
    else:
        pytest.fail(f"No relation found for {planner_app}:planner")

    response = poll_flavor_status(unit_ip, flavor_name, user_token, requests.status_codes.codes.ok)
    assert response.status_code == requests.status_codes.codes.ok

    juju.cli("remove-relation", f"{planner_app}:planner", github_runner_app)
    juju.wait(
        lambda state: jubilant.all_active(state, planner_app),
        timeout=6 * 60,
        delay=10,
    )

    response = poll_flavor_status(unit_ip, flavor_name, user_token, requests.status_codes.codes.not_found)
    assert response.status_code == requests.status_codes.codes.not_found


@pytest.mark.usefixtures("planner_with_integrations")
def test_planner_enable_disable_flavor_actions(
    juju: jubilant.Juju,
    planner_app: str,
    user_token: str,
):
    """
    arrange: The planner app is deployed with required integrations and a flavor exists.
    act: Run disable-flavor and enable-flavor actions.
    assert: Flavor is disabled and enabled correctly as verified via API.
    """
    status = juju.status()
    unit_ip = status.apps[planner_app].units[planner_app + "/0"].address
    flavor_name = "test-action-flavor"

    # Create a test flavor
    response = requests.post(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        json={
            "platform": "github",
            "labels": ["self-hosted", "linux"],
            "priority": 50,
            "minimum_pressure": 0,
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}",
        },
        timeout=30,
    )
    assert response.status_code == requests.status_codes.codes.created

    # Verify flavor is initially enabled
    response = requests.get(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=30,
    )
    assert response.status_code == requests.status_codes.codes.OK
    flavor_data = response.json()
    assert flavor_data["is_disabled"] is False, "Flavor should be enabled initially"

    # Run action to disable the flavor
    unit_name = f"{planner_app}/0"
    result = juju.run(
        unit_name,
        "disable-flavor",
        params={"flavor": flavor_name},
    )
    assert result.status == "completed", f"Action failed: {result.results}"
    assert "successfully" in result.results.get("message", "").lower()

    # Verify flavor is now disabled
    response = requests.get(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=30,
    )
    assert response.status_code == requests.status_codes.codes.OK
    flavor_data = response.json()
    assert flavor_data["is_disabled"] is True, "Flavor should be disabled after action"

    # Run action to enable the flavor
    result = juju.run(
        unit_name,
        "enable-flavor",
        params={"flavor": flavor_name},
    )
    assert result.status == "completed", f"Action failed: {result.results}"
    assert "successfully" in result.results.get("message", "").lower()

    # Verify flavor is enabled again
    response = requests.get(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=30,
    )
    assert response.status_code == requests.status_codes.codes.OK
    flavor_data = response.json()
    assert flavor_data["is_disabled"] is False, "Flavor should be enabled after action"


def poll_flavor_status(unit_ip, flavor_name, token, expected_status, attempts=24, interval=5):
    """Poll the flavor API until the expected HTTP status is returned."""
    for _ in range(attempts):
        response = requests.get(
            f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code == expected_status:
            return response
        time.sleep(interval)
    return response
