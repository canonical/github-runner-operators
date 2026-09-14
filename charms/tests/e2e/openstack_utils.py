# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Nova checks for the GARM E2E removal scenario.

The removal scenario asserts that a *live* runner VM leaves the tenant once the
GARM charm is removed through the normal Juju path. Talking to Nova through
openstacksdk -- the same library stack the workflow already installs via
``python-openstackclient`` for its preflight checks and orphan sweep -- replaces
the hand-rolled Keystone v3 auth and raw ``/servers/detail`` REST calls.
"""

from __future__ import annotations

import logging
from typing import Any

import openstack
import pytest
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_delay,
    wait_fixed,
)

logger = logging.getLogger(__name__)

# Cadence for the tenacity-backed Nova state wait.
NOVA_SERVER_POLL_INTERVAL = 10


def _connect(credentials: dict[str, str]) -> Any:
    """Authenticate to Keystone and return an openstacksdk connection."""
    return openstack.connect(
        auth_url=credentials["auth_url"],
        username=credentials["username"],
        password=credentials["password"],
        project_name=credentials["project_name"],
        user_domain_name=credentials["user_domain_name"],
        project_domain_name=credentials["project_domain_name"],
        region_name=credentials["region_name"],
        identity_api_version=3,
    )


class _ServerStateNotReached(Exception):
    """Raised between polls until the Nova server reaches the awaited state.

    Carries the last matching servers for the failure report.
    """

    def __init__(self, servers: list[Any]) -> None:
        super().__init__("Nova server state not reached yet")
        self.servers = servers


def _server_state_reached(connection: Any, server_name: str, present: bool) -> None:
    """One poll: verify the exact GARM server is present or absent in Nova.

    Raises _ServerStateNotReached until the awaited state holds, which the
    tenacity retry in wait_for_server_state turns into another poll.
    """
    servers = list(connection.compute.servers(name=server_name))
    exists = any(item.name == server_name for item in servers)
    if exists == present:
        logger.info(
            "Nova server %s is %s",
            server_name,
            "present" if present else "absent",
        )
        return
    raise _ServerStateNotReached(servers)


def wait_for_server_state(
    credentials: dict[str, str],
    server_name: str,
    present: bool,
    timeout: int,
    poll_interval: int = NOVA_SERVER_POLL_INTERVAL,
) -> None:
    """Wait until the exact GARM server is present or absent in Nova.

    Tenacity polls _server_state_reached every ``poll_interval`` seconds until
    ``timeout`` elapses; _ServerStateNotReached (with the last matching
    servers) carries the diagnostics for the failure report.

    Args:
        credentials: OpenStack tenant configuration (OS_* values).
        server_name: Nova server (instance) name to look for.
        present: True waits for the server to exist, False for it to be gone.
        timeout: Maximum seconds to wait before failing the test.
        poll_interval: Seconds between polls.
    """
    connection = _connect(credentials)
    try:
        Retrying(
            stop=stop_after_delay(timeout),
            wait=wait_fixed(poll_interval),
            retry=retry_if_exception_type(_ServerStateNotReached),
            reraise=True,
        )(_server_state_reached, connection, server_name, present)
    except _ServerStateNotReached as exc:
        pytest.fail(
            f"Nova server {server_name!r} did not become "
            f"{'present' if present else 'absent'}; last response contained "
            f"{len(exc.servers)} matching server(s)"
        )
