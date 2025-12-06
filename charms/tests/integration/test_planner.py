# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import jubilant
import pytest
import requests

APP_PORT = 8080
METRICS_PORT = 9464


@pytest.mark.usefixtures("postgresql")
def test_planner_postgresql_integration(
    juju: jubilant.Juju,
    planner_app: str,
):
    """
    arrange: The planner app and postgresql deployed and integrated with each other.
    act: Send a http request to the planner app.
    assert: Assert that the server responds with a status code of 200
    """

    status = juju.status()
    unit_ip = status.apps[planner_app].units[planner_app + "/0"].address
    response = requests.post(
        f"http://{unit_ip}:{APP_PORT}/api/v1/flavors/",
        json={
            "platform": "github",
            "labels": ["self-hosted", "amd64"],
            "priority": 100,
            "minimum_pressure": 0,
        },
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == requests.status_codes.codes.OK


def test_planner_prometheus_metrics(
    juju: jubilant.Juju,
    planner_app: str,
):
    """
    arrange: The planner app is deployed.
    act: Get Prometheus metrics from the charm.
    assert: Assert that the server responds with a status code of 200
    """
    status = juju.status()
    unit_ip = status.apps[planner_app].units[planner_app + "/0"].address
    response = requests.get(f"http://{unit_ip}:{METRICS_PORT}/metrics")

    assert response.status_code == requests.status_codes.codes.OK
