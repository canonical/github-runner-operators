# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import jubilant
import requests

APP_PORT = 8080


def test_rabbitmq_server_integration(
    juju: jubilant.Juju,
    app: str,
    rabbitmq_server_app: str,
):
    """
    arrange: The app and rabbitmq deployed
    act: Integrate the app with rabbitmq and send a http request
    assert: Assert that the server responds with a status code of 200
    """
    juju.integrate(app, rabbitmq_server_app)
    juju.wait(
        lambda status: jubilant.all_active(status, app),
        timeout=(10 * 60),
        delay=30,
    )

    status = juju.status()
    unit_ip = status.apps[app].units[app + "/0"].address
    response = requests.post(
        f"http://{unit_ip}:{APP_PORT}/webhook",
        data='{"message":"Hello, Alice!"}',
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "0aca2d7154cddad4f56f246cad61f1485df"
            "34b8056e10c4e4799494376fb3413",
        },
    )

    assert response.status_code == requests.status_codes.codes.OK
