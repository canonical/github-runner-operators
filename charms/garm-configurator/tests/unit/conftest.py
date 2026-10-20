# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures for the charm's unit tests."""

import pytest

DEFAULT_SECURITY_GROUP_ID = "sg-1234"


@pytest.fixture(autouse=True)
def security_group_calls(monkeypatch):
    """Keep the charm's OpenStack calls out of the unit tests.

    ops applies the charmcraft default of ``security-group-rules``, so every reconcile
    manages the scale set's security group. A test that cares about the call asks for this
    fixture and inspects the recorded calls; one that cares about a failure replaces the
    reconciler itself.
    """
    calls = []

    class _FakeReconciler:
        def __init__(self, provider_config):
            calls.append(("init", provider_config))

        def reconcile(self, name, rules):
            calls.append((name, rules))
            return DEFAULT_SECURITY_GROUP_ID

    monkeypatch.setattr("charm.SecurityGroupReconciler", _FakeReconciler)
    return calls
