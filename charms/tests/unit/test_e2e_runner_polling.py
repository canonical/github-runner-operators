# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Model-free regression tests for E2E runner discovery."""

from unittest.mock import Mock

import pytest

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
    monkeypatch.setattr(e2e.time, "time", Mock(side_effect=[0, 1, 100]))
    monkeypatch.setattr(e2e.time, "sleep", Mock())
    monkeypatch.setattr(e2e, "_collect_debug_info", Mock())

    e2e._wait_for_runner_online(Mock(), "garm", label, timeout=10)

    assert [call.args[0] for call in get.call_args_list] == [
        "http://garm:8080/api/v1/scalesets",
        "http://garm:8080/api/v1/scalesets/5/instances",
    ]
