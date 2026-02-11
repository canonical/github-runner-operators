# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit test for planner client."""

import pytest
import requests

from planner import PlannerClient, PlannerError

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


def test_list_flavor_names_returns_names(requests_mock: object) -> None:
    """
    arrange: A requests mock for GET request to the /api/v1/flavors endpoint.
    act: The list_flavor_names method of the PlannerClient is called.
    assert: The returned list of flavor names matches the expected list.
    """
    requests_mock.get(f"{base_url}/api/v1/flavors", json={"names": ["small", "large"]})
    client = PlannerClient(base_url=base_url, admin_token="token")

    assert client.list_flavor_names() == ["small", "large"]


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


def test_delete_flavor_completes_successfully(requests_mock: object) -> None:
    """
    arrange: A requests mock for DELETE request to the /api/v1/flavors/{name} endpoint.
    act: The delete_flavor method of the PlannerClient is called.
    assert: The method completes successfully without raising an exception.
    """
    requests_mock.delete(f"{base_url}/api/v1/flavors/small", status_code=200)
    client = PlannerClient(base_url=base_url, admin_token="token")

    client.delete_flavor("small")


def test_http_error_raises_planner_error(requests_mock: object) -> None:
    """
    arrange: A requests mock that returns 400.
    act: The list_auth_token_names method of the PlannerClient is called.
    assert: A PlannerError is raised with the expected message.
    """
    requests_mock.get(f"{base_url}/api/v1/auth/token", status_code=400, text="bad request")
    client = PlannerClient(base_url=base_url, admin_token="token")

    with pytest.raises(PlannerError, match="HTTP error 400"):
        client.list_auth_token_names()


def test_connection_error_raises_runtime_error(requests_mock: object) -> None:
    """
    arrange: A requests mock that raises a connection error.
    act: The list_auth_token_names method of the PlannerClient is called.
    assert: A RuntimeError is raised with the expected message.
    """
    requests_mock.get(
        f"{base_url}/api/v1/auth/token",
        exc=requests.exceptions.ConnectionError("boom"),
    )
    client = PlannerClient(base_url=base_url, admin_token="token")

    with pytest.raises(RuntimeError, match="Connection error"):
        client.list_auth_token_names()
