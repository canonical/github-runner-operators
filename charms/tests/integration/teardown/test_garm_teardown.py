# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM charm teardown integration tests on ProdStack."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import jubilant
import pytest
import requests
from tests.e2e.conftest import GARM_API_PORT, _garm_login, _get_garm_address

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OS_AUTH_URL"),
    reason="requires the ProdStack E2E environment",
)


def _wait_for_provider_running_instance(
    juju: jubilant.Juju, garm_app: str, scaleset_name: str, timeout: int = 25 * 60
) -> dict[str, Any]:
    """Wait for the GARM provider to report one real runner instance as running."""
    deadline = time.monotonic() + timeout
    last_instances: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        address = _get_garm_address(juju, garm_app)
        base_url = f"http://{address}:{GARM_API_PORT}/api/v1"
        token = _garm_login(juju, address)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            scalesets_response = requests.get(
                f"{base_url}/scalesets", headers=headers, timeout=30
            )
            scalesets_response.raise_for_status()
            scaleset = next(
                (
                    item
                    for item in scalesets_response.json()
                    if item.get("name") == scaleset_name
                ),
                None,
            )
            if scaleset is not None:
                instances_response = requests.get(
                    f"{base_url}/scalesets/{scaleset['id']}/instances",
                    headers=headers,
                    timeout=30,
                )
                instances_response.raise_for_status()
                last_instances = instances_response.json() or []
                for instance in last_instances:
                    if instance.get("status") == "running":
                        logger.info(
                            "Observed provider-running GARM instance %s (runner_status=%s)",
                            instance.get("name"),
                            instance.get("runner_status"),
                        )
                        return instance
        except (requests.RequestException, ValueError, KeyError) as exc:
            logger.info("Waiting for a provider-running instance: %s", exc)
        time.sleep(15)

    pytest.fail(
        f"No provider-running instance appeared in {scaleset_name!r}; "
        f"last observed instances: {last_instances!r}"
    )


def _openstack_endpoint_and_token(credentials: dict[str, str]) -> tuple[str, str]:
    """Authenticate to Keystone and return the compute endpoint and token."""
    auth_url = credentials["auth_url"].rstrip("/")
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": credentials["username"],
                        "domain": {"name": credentials["user_domain_name"]},
                    }
                },
            },
            "scope": {
                "project": {
                    "name": credentials["project_name"],
                    "domain": {"name": credentials["project_domain_name"]},
                }
            },
        }
    }
    response = requests.post(f"{auth_url}/auth/tokens", json=payload, timeout=30)
    response.raise_for_status()
    token = response.headers.get("X-Subject-Token")
    assert token, "Keystone did not return a subject token"

    catalog = response.json()["token"]["catalog"]
    compute = next(service for service in catalog if service.get("type") == "compute")
    endpoints = compute.get("endpoints", [])
    region = credentials["region_name"]
    endpoint = next(
        (
            item["url"]
            for item in endpoints
            if item.get("region") == region and item.get("interface") == "public"
        ),
        None,
    )
    if endpoint is None:
        endpoint = next(
            (item["url"] for item in endpoints if item.get("region") == region),
            None,
        )
    assert endpoint, f"No compute endpoint was returned for region {region!r}"
    return endpoint.rstrip("/"), token


def _wait_for_openstack_server_state(
    credentials: dict[str, str], server_name: str, present: bool, timeout: int
) -> None:
    """Wait until the exact GARM server is present or absent in Nova."""
    endpoint, token = _openstack_endpoint_and_token(credentials)
    deadline = time.monotonic() + timeout
    last_servers: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        response = requests.get(
            f"{endpoint}/servers/detail",
            params={"name": server_name},
            headers={"X-Auth-Token": token},
            timeout=30,
        )
        response.raise_for_status()
        last_servers = response.json().get("servers", [])
        exists = any(item.get("name") == server_name for item in last_servers)
        if exists == present:
            logger.info(
                "Nova server %s is %s",
                server_name,
                "present" if present else "absent",
            )
            return
        time.sleep(10)

    pytest.fail(
        f"Nova server {server_name!r} did not become "
        f"{'present' if present else 'absent'}; last response contained "
        f"{len(last_servers)} matching server(s)"
    )


def test_garm_charm_removal_drains_provider_runner(
    juju: jubilant.Juju,
    garm_with_ingress: str,
    e2e_scaleset: str,
    openstack_credentials: dict[str, str],
) -> None:
    """Remove GARM normally and verify its live runner is removed from Nova."""
    instance = _wait_for_provider_running_instance(
        juju, garm_with_ingress, e2e_scaleset
    )
    server_name = instance.get("name")
    assert server_name, f"GARM instance did not include a provider name: {instance!r}"
    _wait_for_openstack_server_state(
        openstack_credentials, server_name, present=True, timeout=120
    )

    logger.info("Removing disposable GARM application through the normal Juju path")
    juju.remove_application(garm_with_ingress)
    juju.wait(
        lambda status: garm_with_ingress not in status.apps,
        timeout=15 * 60,
        delay=10,
    )

    _wait_for_openstack_server_state(
        openstack_credentials, server_name, present=False, timeout=10 * 60
    )
