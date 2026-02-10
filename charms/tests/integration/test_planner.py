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
    response = requests.get(f"http://{unit_ip}:{METRICS_PORT}/metrics")

    assert response.status_code == requests.status_codes.codes.OK


def test_planner_github_runner_integration(
    juju: jubilant.Juju,
    planner_app: str,
    any_charm_github_runner_app: str,
):
    """
    arrange: The planner app and any-charm app mocking github-runner is deployed.
    act: The planner app and a github-runner app deployed and integrated with each other.
    assert: The integration data contains the endpoint and auth token.
    """
    github_runner_app = any_charm_github_runner_app
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
            return
    else:
        pytest.fail(f"No relation found for {planner_app}:planner")


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
    )
    assert response.status_code == requests.status_codes.codes.created

    # Verify flavor is initially enabled
    response = requests.get(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        headers={"Authorization": f"Bearer {user_token}"},
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
    )
    assert response.status_code == requests.status_codes.codes.OK
    flavor_data = response.json()
    assert flavor_data["is_disabled"] is False, "Flavor should be enabled after action"


@pytest.mark.usefixtures("planner_with_integrations")
def test_planner_deletes_flavor_on_relation_removed(
    juju: jubilant.Juju,
    planner_app: str,
    any_charm_github_runner_with_flavor_app: str,
    user_token: str,
):
    """
    arrange: Planner and a github-runner mock charm that sets relation flavor data.
    act: Remove the planner relation from the github-runner mock.
    assert: The managed flavor is deleted by planner relation cleanup.
    """
    status = juju.status()
    unit_ip = status.apps[planner_app].units[f"{planner_app}/0"].address
    github_runner_app = any_charm_github_runner_with_flavor_app
    flavor_name = "test-relation-flavor"

    response = requests.post(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
        json={
            "platform": "github",
            "labels": ["self-hosted", "linux"],
            "priority": 75,
            "minimum_pressure": 0,
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {user_token}",
        },
    )
    assert response.status_code in (
        requests.status_codes.codes.created,
        requests.status_codes.codes.conflict,
    )

    juju.integrate(f"{planner_app}:planner", github_runner_app)
    juju.wait(
        lambda state: jubilant.all_active(state, planner_app),
        timeout=6 * 60,
        delay=10,
    )

    juju.cli("remove-relation", f"{planner_app}:planner", github_runner_app)
    juju.wait(
        lambda state: jubilant.all_active(state, planner_app),
        timeout=6 * 60,
        delay=10,
    )

    for _ in range(24):
        response = requests.get(
            f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/{flavor_name}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        if response.status_code == requests.status_codes.codes.not_found:
            break
        time.sleep(5)

    assert response.status_code == requests.status_codes.codes.not_found
