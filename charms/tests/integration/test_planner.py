# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
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
    
    # WIP
    status = juju.status()
    
    print("############################################################################################")
    print(status)
    print( status[github_runner_app].relations)
    print("############################################################################################")