# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit test for planner client."""

import pytest
import requests

from planner import Flavor, PlannerClient, PlannerError

base_url = "http://127.0.0.1:8080"


def test_list_auth_token_names_returns_names(requests_mock: object) -> None:
    """
    arrange: A requests mock for GET request to the /api/v1/auth/token endpoint.
    act: The list_auth_token_names method of the PlannerClient is called.
    assert: The returned list of token names matches the expected list.
    """
    requests_mock.get(f"{base_url}/api/v1/auth/token", json={"names": ["one", "two"]})
    client = PlannerClient(base_url=base_url, admin_token="token")

    assert client.list_auth_token_names() == ["one", "two"]


def test_create_auth_token_returns_token(requests_mock: object) -> None:
    """
    arrange: A requests mock for POST request to the /api/v1/auth/token/{name} endpoint.
    act: The create_auth_token method of the PlannerClient is called.
    assert: The returned token matches the expected token.
    """
    requests_mock.post(f"{base_url}/api/v1/auth/token/runner", json={"token": "secret"})
    client = PlannerClient(base_url=base_url, admin_token="token")

    assert client.create_auth_token("runner") == "secret"


def test_update_flavor_completes_successfully(requests_mock: object) -> None:
    """
    arrange: A requests mock for PATCH request to the /api/v1/flavors/{name} endpoint.
    act: The update_flavor method of the PlannerClient is called.
    assert: The method completes successfully without raising an exception.
    """
    requests_mock.patch(f"{base_url}/api/v1/flavors/small", status_code=200)
    client = PlannerClient(base_url=base_url, admin_token="token")

    client.update_flavor("small", True)


def test_create_flavor_completes_successfully(requests_mock: object) -> None:
    """
    arrange: A requests mock for POST request to the /api/v1/flavors/{name} endpoint.
    act: The create_flavor method of the PlannerClient is called.
    assert: The method completes successfully without raising an exception.
    """
    requests_mock.post(f"{base_url}/api/v1/flavors/small", status_code=201)
    client = PlannerClient(base_url=base_url, admin_token="token")

    client.create_flavor(
        flavor_name="small",
        platform="github",
        labels=["self-hosted", "linux"],
        priority=100,
        minimum_pressure=0,
    )


def test_delete_auth_token_completes_successfully(requests_mock: object) -> None:
    """
    arrange: A requests mock for DELETE request to the /api/v1/auth/token/{name} endpoint.
    act: The delete_auth_token method of the PlannerClient is called.
    assert: The method completes successfully without raising an exception.
    """
    requests_mock.delete(f"{base_url}/api/v1/auth/token/runner", status_code=204)
    client = PlannerClient(base_url=base_url, admin_token="token")

    client.delete_auth_token("runner")


def test_list_flavors_returns_flavor_list(requests_mock: object) -> None:
    """
    arrange: A requests mock for GET request to the /api/v1/flavors endpoint.
    act: The list_flavors method of the PlannerClient is called.
    assert: The returned list matches the expected Flavor objects.
    """
    flavor_data = [
        {
            "name": "small",
            "platform": "github",
            "labels": ["self-hosted", "linux"],
            "priority": 100,
            "is_disabled": False,
            "minimum_pressure": 0,
        },
        {
            "name": "large",
            "platform": "github",
            "labels": ["self-hosted", "linux", "x64"],
            "priority": 200,
            "is_disabled": True,
            "minimum_pressure": 10,
        },
    ]
    requests_mock.get(f"{base_url}/api/v1/flavors", json=flavor_data)
    client = PlannerClient(base_url=base_url, admin_token="token")

    assert client.list_flavors() == [
        Flavor(
            name="small",
            platform="github",
            labels=["self-hosted", "linux"],
            priority=100,
            minimum_pressure=0,
            is_disabled=False,
        ),
        Flavor(
            name="large",
            platform="github",
            labels=["self-hosted", "linux", "x64"],
            priority=200,
            minimum_pressure=10,
            is_disabled=True,
        ),
    ]


def test_list_flavors_raises_planner_error_on_http_error(requests_mock: object) -> None:
    """
    arrange: A requests mock that returns 500 for the flavor list endpoint.
    act: The list_flavors method of the PlannerClient is called.
    assert: A PlannerError is raised.
    """
    requests_mock.get(f"{base_url}/api/v1/flavors", status_code=500, text="server error")
    client = PlannerClient(base_url=base_url, admin_token="token")

    with pytest.raises(PlannerError, match="HTTP error 500") as exc_info:
        client.list_flavors()
    assert exc_info.value.status_code == 500


def test_delete_flavor_completes_successfully(requests_mock: object) -> None:
    """
    arrange: A requests mock for DELETE request to the /api/v1/flavors/{name} endpoint.
    act: The delete_flavor method of the PlannerClient is called.
    assert: The method completes successfully without raising an exception.
    """
    requests_mock.delete(f"{base_url}/api/v1/flavors/small", status_code=200)
    client = PlannerClient(base_url=base_url, admin_token="token")

    client.delete_flavor("small")


def test_delete_flavor_succeeds_when_not_found(requests_mock: object) -> None:
    """
    arrange: A requests mock that returns 404 for the flavor DELETE endpoint.
    act: The delete_flavor method of the PlannerClient is called.
    assert: The method completes without raising an exception.
    """
    requests_mock.delete(f"{base_url}/api/v1/flavors/gone", status_code=404, text="not found")
    client = PlannerClient(base_url=base_url, admin_token="token")

    client.delete_flavor("gone")


def test_http_error_raises_planner_error(requests_mock: object) -> None:
    """
    arrange: A requests mock that returns 400.
    act: The list_auth_token_names method of the PlannerClient is called.
    assert: A PlannerError is raised with the expected message.
    """
    requests_mock.get(f"{base_url}/api/v1/auth/token", status_code=400, text="bad request")
    client = PlannerClient(base_url=base_url, admin_token="token")

    with pytest.raises(PlannerError, match="HTTP error 400") as exc_info:
        client.list_auth_token_names()
    assert exc_info.value.status_code == 400


def test_connection_error_raises_planner_error(requests_mock: object) -> None:
    """
    arrange: A requests mock that raises a connection error.
    act: The list_auth_token_names method of the PlannerClient is called.
    assert: A PlannerError is raised with status_code 0 and a connection error message.
    """
    requests_mock.get(
        f"{base_url}/api/v1/auth/token",
        exc=requests.exceptions.ConnectionError("boom"),
    )
    client = PlannerClient(base_url=base_url, admin_token="token")

    with pytest.raises(PlannerError, match="Connection error") as exc_info:
        client.list_auth_token_names()
    assert exc_info.value.status_code == 0
