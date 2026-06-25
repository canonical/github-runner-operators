#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Minimal fake debug-ssh provider for GARM integration tests."""

import ops


class FakeDebugSshCharm(ops.CharmBase):
    """Fake charm providing the debug-ssh relation for testing."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self.framework.observe(
            self.on.provide_debug_ssh_relation_joined,
            self._on_debug_ssh_joined,
        )
        self.unit.status = ops.ActiveStatus()

    def _on_debug_ssh_joined(self, event: ops.RelationJoinedEvent) -> None:
        """Write hard-coded tmate server data into the relation databag."""
        event.relation.data[self.unit]["host"] = "tmate.example.com"
        event.relation.data[self.unit]["port"] = "2200"
        event.relation.data[self.unit]["rsa_fingerprint"] = "SHA256:fakefingerprint1234"
        event.relation.data[self.unit]["ed25519_fingerprint"] = "SHA256:fakeed25519abcd"
        self.unit.status = ops.ActiveStatus()


if __name__ == "__main__":
    ops.main(FakeDebugSshCharm)
