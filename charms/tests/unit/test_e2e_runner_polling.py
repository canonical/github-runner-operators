# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Model-free regression tests for E2E runner discovery and removal scenarios."""

from unittest.mock import Mock

import pytest
from tests.e2e import conftest as fixtures
from tests.e2e import openstack as os_mod
from tests.e2e import test_garm_e2e as e2e


@pytest.mark.parametrize("name", ["e2e-f624f0", "e2e-f624f0-d0f3c26d"])
def test_runner_polling_resolves_enabled_scaleset_by_label(monkeypatch, name):
    """
    arrange: Legacy or hashed scale-set names, unrelated sets, and draining generations.
    act: Wait for the unique E2E label using mocked GARM API responses.
    assert: Poll the enabled matching set by ID, so naming changes cannot hide its runner.
    """
    label = "e2e-f624f0"
    matching_tags = [{"name": label}]
    scalesets = [
        {"id": 1, "name": label, "enabled": True, "tags": [{"name": "other"}]},
        {"id": 2, "name": "draining", "enabled": False, "tags": matching_tags},
        {"id": 3, "name": "omitted-enabled", "tags": matching_tags},
        {"id": 4, "name": "no-tags", "enabled": True, "tags": None},
        {"id": 5, "name": name, "enabled": True, "tags": matching_tags},
    ]
    get = Mock(
        side_effect=[
            Mock(status_code=200, json=Mock(return_value=scalesets)),
            Mock(json=Mock(return_value=[{"name": "runner", "runner_status": "idle"}])),
        ]
    )
    monkeypatch.setattr(e2e.requests, "get", get)
    monkeypatch.setattr(e2e, "_get_garm_address", Mock(return_value="garm"))
    monkeypatch.setattr(e2e, "_garm_login", Mock(return_value="token"))
    monkeypatch.setattr(e2e, "_collect_debug_info", Mock())
    monkeypatch.setattr(e2e, "GARM_TOKEN_CACHE", {})
    monkeypatch.setattr(e2e, "LAST_INSTANCE_SUMMARIES", {})

    e2e._wait_for_runner_online(Mock(), "garm", label, timeout=10)

    assert [call.args[0] for call in get.call_args_list] == [
        "http://garm:8080/api/v1/scalesets",
        "http://garm:8080/api/v1/scalesets/5/instances",
    ]


@pytest.mark.parametrize("name", ["e2e-f624f0", "e2e-f624f0-d0f3c26d"])
def test_teardown_removes_all_generations_for_label(monkeypatch, name):
    """
    arrange: Active and disabled scale sets with the run label plus unrelated sets.
    act: Tear down the E2E scale sets with no remaining instances.
    assert: Delete every matching generation by ID while preserving unrelated sets.
    """
    label = "e2e-f624f0"
    tags = [{"name": label}]
    scalesets = [
        {"id": 1, "name": label, "tags": [{"name": "other"}]},
        {"id": 2, "name": name, "enabled": True, "tags": tags},
        {"id": 3, "name": "disabled-generation", "enabled": False, "tags": tags},
        {"id": 4, "name": "omitted-enabled", "tags": tags},
        {"id": 5, "name": "no-tags", "tags": None},
    ]
    get = Mock(
        side_effect=[
            Mock(json=Mock(return_value=scalesets)),
            *[Mock(json=Mock(return_value=[])) for _ in range(3)],
        ]
    )
    put, delete = Mock(), Mock()
    monkeypatch.setattr(fixtures.requests, "get", get)
    monkeypatch.setattr(fixtures.requests, "put", put)
    monkeypatch.setattr(fixtures.requests, "delete", delete)
    monkeypatch.setattr(fixtures, "_get_garm_address", Mock(return_value="garm"))
    monkeypatch.setattr(fixtures, "_garm_login", Mock(return_value="token"))

    fixtures._drain_and_delete_scaleset(Mock(), "garm", label)

    expected = [f"http://garm:8080/api/v1/scalesets/{id}" for id in (2, 3, 4)]
    assert [call.args[0] for call in put.call_args_list] == expected
    assert [call.args[0] for call in delete.call_args_list] == expected
    assert [call.args[0] for call in get.call_args_list[1:]] == [
        f"{url}/instances" for url in expected
    ]


def test_wait_for_runner_online_fails_with_debug_info(monkeypatch):
    """On timeout the wait reports the last state and collects debug info."""
    monkeypatch.setattr(
        e2e,
        "_registered_runner",
        Mock(side_effect=e2e._RunnerNotRegistered([])),
    )
    monkeypatch.setattr(e2e, "_collect_debug_info", Mock())
    monkeypatch.setattr(e2e, "GARM_TOKEN_CACHE", {})

    with pytest.raises(pytest.fail.Exception):
        e2e._wait_for_runner_online(
            Mock(), "garm", "e2e-f624f0", timeout=0.2, poll_interval=0.01
        )

    e2e._collect_debug_info.assert_called_once()


def test_provider_running_instance_wait_succeeds(monkeypatch):
    """A provider-running instance in the label's scale set ends the wait."""
    label = "e2e-f624f0"
    get = Mock(
        side_effect=[
            Mock(
                status_code=200,
                json=Mock(
                    return_value=[
                        {
                            "id": 5,
                            "name": label,
                            "enabled": True,
                            "tags": [{"name": label}],
                        }
                    ]
                ),
            ),
            Mock(
                json=Mock(
                    return_value=[
                        {"name": "vm", "status": "running", "runner_status": "idle"}
                    ]
                )
            ),
        ]
    )
    monkeypatch.setattr(e2e.requests, "get", get)
    monkeypatch.setattr(e2e, "_get_garm_address", Mock(return_value="garm"))
    monkeypatch.setattr(e2e, "_garm_login", Mock(return_value="token"))
    monkeypatch.setattr(e2e, "GARM_TOKEN_CACHE", {})

    instance = e2e._wait_for_provider_running_instance(
        Mock(), "garm", label, timeout=10
    )

    assert instance["name"] == "vm"
    assert [call.args[0] for call in get.call_args_list] == [
        "http://garm:8080/api/v1/scalesets",
        "http://garm:8080/api/v1/scalesets/5/instances",
    ]


def test_provider_running_instance_wait_fails_on_timeout(monkeypatch):
    """No provider-running instance within the deadline fails the test."""
    monkeypatch.setattr(
        e2e,
        "_running_instance",
        Mock(
            side_effect=e2e._InstanceNotRunning([{"name": "vm", "status": "building"}])
        ),
    )
    monkeypatch.setattr(e2e, "GARM_TOKEN_CACHE", {})

    with pytest.raises(pytest.fail.Exception):
        e2e._wait_for_provider_running_instance(
            Mock(), "garm", "e2e-f624f0", timeout=0.2, poll_interval=0.01
        )


class _FakeServer:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeCompute:
    def __init__(self, active: bool) -> None:
        self._active = active

    def servers(self, name: str):
        return [_FakeServer(name)] if self._active else []


class _FakeConnection:
    def __init__(self, active: bool) -> None:
        self.compute = _FakeCompute(active)


def test_wait_for_server_state_present(monkeypatch):
    """A server that exists satisfies the present wait on the first poll."""
    monkeypatch.setattr(
        os_mod, "_connect", Mock(return_value=_FakeConnection(active=True))
    )
    os_mod.wait_for_server_state({}, "srv", present=True, timeout=2, poll_interval=0.01)


def test_wait_for_server_state_absent(monkeypatch):
    """A server that is gone satisfies the absent wait on the first poll."""
    monkeypatch.setattr(
        os_mod, "_connect", Mock(return_value=_FakeConnection(active=False))
    )
    os_mod.wait_for_server_state(
        {}, "srv", present=False, timeout=2, poll_interval=0.01
    )


def test_wait_for_server_state_times_out(monkeypatch):
    """A server that never reaches the awaited state fails the test."""
    monkeypatch.setattr(
        os_mod, "_connect", Mock(return_value=_FakeConnection(active=False))
    )

    with pytest.raises(pytest.fail.Exception):
        os_mod.wait_for_server_state(
            {}, "srv", present=True, timeout=0.2, poll_interval=0.01
        )
