# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for pre-remove GARM resource cleanup."""

from types import SimpleNamespace

from resource_cleanup import GarmResourceCleanup


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
