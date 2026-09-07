# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for pre-remove GARM resource cleanup."""

from types import SimpleNamespace

import pytest

from garm_api import GarmNotFoundError
from resource_cleanup import GarmCleanupError, GarmResourceCleanup


class _FakeClient:
    def __init__(self, instance_lists):
        self.scalesets = [SimpleNamespace(id=7, name="stale", enabled=True)]
        self.instance_lists = iter(instance_lists)
        self.events = []

    def list_scalesets(self):
        return self.scalesets

    def update_scaleset(self, scaleset_id, params):
        self.events.append(("disable", scaleset_id, params.enabled, params.min_idle_runners))

    def list_scale_set_instances(self, scaleset_id):
        self.events.append(("list", scaleset_id))
        return next(self.instance_lists)

    def delete_instance(self, instance_name, *, force_remove=False, bypass_gh_unauthorized=False):
        self.events.append(
            ("delete-instance", instance_name, force_remove, bypass_gh_unauthorized)
        )

    def delete_scaleset(self, scaleset_id):
        self.events.append(("delete-scaleset", scaleset_id))
        self.scalesets = []


def test_cleanup_drains_runners_before_deleting_scaleset():
    """
    arrange: A scaleset whose runner list is populated, then empty on the next poll.
    act: Run cleanup.
    assert: The runner is requested for deletion before the now-empty scaleset is deleted.
    """
    client = _FakeClient(
        [
            [SimpleNamespace(name="runner-1", status="running")],
            [],
        ]
    )

    GarmResourceCleanup(
        client,
        timeout=1,
        poll_interval=0,
        sleep=lambda _: None,
        monotonic=lambda: 0,
    ).run()

    assert client.events == [
        ("disable", 7, False, 0),
        ("list", 7),
        ("delete-instance", "runner-1", False, False),
        ("disable", 7, False, 0),
        ("list", 7),
        ("delete-scaleset", 7),
    ]


class _ScalesetAlreadyGoneClient(_FakeClient):
    def update_scaleset(self, scaleset_id, params):
        raise GarmNotFoundError(f"scaleset {scaleset_id} was already removed")


def test_cleanup_treats_scaleset_removed_during_drain_as_success():
    """
    arrange: A scaleset disappears before cleanup can disable it.
    act: Run cleanup after the API reports the scaleset is not found.
    assert: Cleanup treats the already-removed resource as success.
    """
    client = _ScalesetAlreadyGoneClient([[]])

    GarmResourceCleanup(client, timeout=1, sleep=lambda _: None, monotonic=lambda: 0).run()


def test_cleanup_timeout_identifies_blocking_runner_and_operator_action():
    """
    arrange: A scaleset repeatedly reports a runner stuck in pending creation.
    act: Run cleanup until its deadline expires.
    assert: The error identifies the resource, state, and action for the operator.
    """
    client = _FakeClient(
        [
            [SimpleNamespace(name="runner-1", status="pending_create")],
            [SimpleNamespace(name="runner-1", status="pending_create")],
        ]
    )
    clock = iter([0, 0, 2])

    with pytest.raises(
        GarmCleanupError,
        match=(
            r"scaleset 7.*runner runner-1.*pending_create.*"
            r"operator action: inspect the runner state"
        ),
    ):
        GarmResourceCleanup(
            client,
            timeout=1,
            poll_interval=0,
            sleep=lambda _: None,
            monotonic=lambda: next(clock),
        ).run()


def test_cleanup_does_not_redelete_pending_runner():
    """
    arrange: A scaleset whose runner is already pending deletion, then disappears.
    act: Run cleanup.
    assert: Cleanup polls without reissuing runner deletion, then deletes the scaleset.
    """
    client = _FakeClient(
        [
            [SimpleNamespace(name="runner-1", status="pending_delete")],
            [],
        ]
    )

    GarmResourceCleanup(
        client,
        timeout=1,
        poll_interval=0,
        sleep=lambda _: None,
        monotonic=lambda: 0,
    ).run()

    assert client.events == [
        ("disable", 7, False, 0),
        ("list", 7),
        ("disable", 7, False, 0),
        ("list", 7),
        ("delete-scaleset", 7),
    ]
