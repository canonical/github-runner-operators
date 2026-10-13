# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Model-free tests for the E2E runner console capture.

The capture only ever runs when a live E2E run is already failing, so a broken
fetch or a redaction gap would otherwise surface as a lost diagnostic or a leaked
token in a public log -- never as a red test.
"""

import itertools
import logging
from unittest.mock import Mock

import pytest
import requests
from tests.e2e import conftest as fixtures
from tests.e2e import test_garm_e2e as e2e

CREDENTIALS = {
    "auth_url": "https://keystone.example:5000/v3",
    "username": "tenant-bot",
    "password": "tenant-password",
    "project_name": "project",
    "user_domain_name": "Default",
    "project_domain_name": "Default",
    "region_name": "RegionOne",
    "network": "net",
}
COMPUTE_URL = "https://nova.example:8774/v2.1"
RUNNING_VM = {"name": "garm-abc", "status": "running", "provider_id": "server-1"}


def _keystone_response() -> Mock:
    """Build a Keystone token response whose catalog lists compute in two regions."""
    catalog = [
        {
            "type": "compute",
            "endpoints": [
                {"interface": "public", "region_id": "Other", "url": "https://other"},
                {"interface": "internal", "region_id": "RegionOne", "url": "https://int"},
                {"interface": "public", "region_id": "RegionOne", "url": COMPUTE_URL},
            ],
        }
    ]
    return Mock(
        headers={"X-Subject-Token": "keystone-token"},
        json=Mock(return_value={"token": {"catalog": catalog}}),
    )


def _console_response(output: str) -> Mock:
    """Build a Nova os-getConsoleOutput response."""
    return Mock(json=Mock(return_value={"output": output}))


def test_runner_consoles_logs_redacted_console_of_reaped_vm(monkeypatch, caplog):
    """
    arrange: A running runner VM whose console carries the tunnel log line, the tenant
        password, a JWT and a bearer header.
    act: Record the VM while it runs, then log after it is gone from the instance list.
    assert: The tunnel line is logged with every secret redacted -- the snapshot has to
        outlive GARM's reaper, and the log it lands in is public.
    """
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJnYXJtIn0.c2lnbmF0dXJl"
    console = (
        "[e2e-tunnel] ERROR: tunnel never came up\n"
        "login tenant-password\n"
        f"BEARER_TOKEN={jwt}\n"
        "curl -H 'Authorization: Bearer opaque-callback-token' https://garm\n"
        "GITHUB_TOKEN=AABBCCDDEEFF\n"
    )
    post = Mock(side_effect=[_keystone_response(), _console_response(console)])
    monkeypatch.setattr(fixtures.requests, "post", post)
    monkeypatch.setenv("OS_PASSWORD", CREDENTIALS["password"])
    consoles = fixtures.RunnerConsoles(CREDENTIALS)

    consoles.record([RUNNING_VM])
    with caplog.at_level(logging.ERROR):
        consoles.log()

    assert post.call_args_list[1].args[0] == f"{COMPUTE_URL}/servers/server-1/action"
    assert post.call_args_list[1].kwargs["headers"]["X-Auth-Token"] == "keystone-token"
    assert "garm-abc" in caplog.text
    assert "[e2e-tunnel] ERROR: tunnel never came up" in caplog.text
    for secret in ("tenant-password", jwt, "opaque-callback-token", "AABBCCDDEEFF"):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "instances",
    [
        pytest.param([{**RUNNING_VM, "provider_id": None}], id="no-provider-id"),
        pytest.param([{**RUNNING_VM, "status": "creating"}], id="not-running"),
        pytest.param([RUNNING_VM, RUNNING_VM], id="within-refresh-interval"),
    ],
)
def test_runner_consoles_skips_unreadable_or_fresh_vms(monkeypatch, instances):
    """
    arrange: Instances without a server yet, not booted yet, or seen twice in a row.
    act: Record each instance list.
    assert: At most one console read happens, so the poll loop does not hammer Nova.
    """
    post = Mock(side_effect=[_keystone_response(), _console_response("boot")])
    monkeypatch.setattr(fixtures.requests, "post", post)
    consoles = fixtures.RunnerConsoles(CREDENTIALS)

    for instance in instances:
        consoles.record([instance])

    console_reads = [c for c in post.call_args_list if "/servers/" in c.args[0]]
    assert len(console_reads) <= 1


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(requests.ConnectionError("unreachable"), id="unreachable"),
        pytest.param(Mock(headers={}, json=Mock(return_value={})), id="no-token"),
        pytest.param(
            Mock(
                headers={"X-Subject-Token": "t"},
                json=Mock(return_value={"token": {"catalog": []}}),
            ),
            id="no-compute-endpoint",
        ),
    ],
)
def test_runner_consoles_never_raises_on_openstack_errors(monkeypatch, caplog, failure):
    """
    arrange: Keystone unreachable, answering without a token, or without compute.
    act: Record a running VM and log.
    assert: Neither call raises and the failure is logged, so diagnostics cannot turn
        a runner that failed to register into a different, misleading error.
    """
    monkeypatch.setattr(fixtures.requests, "post", Mock(side_effect=[failure]))
    consoles = fixtures.RunnerConsoles(CREDENTIALS)

    with caplog.at_level(logging.WARNING):
        consoles.record([RUNNING_VM])
        consoles.log()

    assert "console" in caplog.text.lower()


def test_wait_for_runner_online_logs_consoles_on_timeout(monkeypatch):
    """
    arrange: A scale set whose only VM runs but never registers.
    act: Wait for a registered runner until the timeout expires.
    assert: Every poll is offered to the console recorder and its snapshots are logged
        before the test fails, while the VM is still up and once it has been reaped.
    """
    scalesets = [{"id": 5, "enabled": True, "tags": [{"name": "e2e-x"}]}]
    get = Mock(
        side_effect=[
            Mock(status_code=200, json=Mock(return_value=scalesets)),
            Mock(json=Mock(return_value=[RUNNING_VM])),
        ]
    )
    monkeypatch.setattr(e2e.requests, "get", get)
    monkeypatch.setattr(e2e, "_get_garm_address", Mock(return_value="garm"))
    monkeypatch.setattr(e2e, "_garm_login", Mock(return_value="token"))
    # Stays past the deadline once reached: logging reads the same patched clock.
    clock = itertools.chain([0, 1], itertools.repeat(100))
    monkeypatch.setattr(e2e.time, "time", Mock(side_effect=clock))
    monkeypatch.setattr(e2e.time, "sleep", Mock())
    monkeypatch.setattr(e2e, "_collect_debug_info", Mock())
    consoles = Mock()

    with pytest.raises(pytest.fail.Exception):
        e2e._wait_for_runner_online(Mock(), "garm", "e2e-x", consoles, timeout=10)

    consoles.record.assert_called_once_with([RUNNING_VM])
    consoles.log.assert_called_once_with()
