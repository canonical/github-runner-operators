# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the charm_state module."""

from unittest.mock import MagicMock

from charm_state import (
    DEBUG_SSH_INTEGRATION_NAME,
    CharmState,
    SSHDebugInfo,
    _get_ssh_debug_connections,
)


def _make_charm(*, relation=None):
    """Build a minimal mock charm."""
    charm = MagicMock()
    charm.model.get_relation.return_value = relation
    return charm


def test_ssh_debug_info_from_charm_no_relation():
    """
    arrange: No debug-ssh relation exists.
    act: Call _get_ssh_debug_connections().
    assert: Returns an empty list.
    """
    charm = _make_charm(relation=None)
    result = _get_ssh_debug_connections(charm)
    assert result == []


def test_ssh_debug_info_from_charm_no_remote_units():
    """
    arrange: debug-ssh relation exists but has no remote units.
    act: Call _get_ssh_debug_connections().
    assert: Returns an empty list.
    """
    relation = MagicMock()
    relation.units = []
    charm = _make_charm(relation=relation)
    result = _get_ssh_debug_connections(charm)
    assert result == []


def test_ssh_debug_info_from_charm_complete_relation_data():
    """
    arrange: debug-ssh relation has one unit with all required fields.
    act: Call _get_ssh_debug_connections().
    assert: Returns one SSHDebugInfo with correct field values.
    """
    unit = MagicMock()
    unit.name = "tmate-ssh-server/0"
    relation = MagicMock()
    relation.units = [unit]
    relation.data = {
        unit: {
            "host": "10.0.0.1",
            "port": "2222",
            "rsa_fingerprint": "SHA256:rsa-fp",
            "ed25519_fingerprint": "SHA256:ed-fp",
        }
    }
    charm = _make_charm(relation=relation)

    result = _get_ssh_debug_connections(charm)

    assert len(result) == 1
    conn = result[0]
    assert conn.host == "10.0.0.1"
    assert conn.port == 2222
    assert conn.rsa_fingerprint == "SHA256:rsa-fp"
    assert conn.ed25519_fingerprint == "SHA256:ed-fp"


def test_ssh_debug_info_from_charm_incomplete_relation_data():
    """
    arrange: debug-ssh relation unit is missing the rsa_fingerprint field.
    act: Call _get_ssh_debug_connections().
    assert: Returns an empty list; the incomplete unit is skipped with a warning.
    """
    unit = MagicMock()
    unit.name = "tmate-ssh-server/0"
    relation = MagicMock()
    relation.units = [unit]
    relation.data = {
        unit: {
            "host": "10.0.0.1",
            "port": "2222",
            # missing rsa_fingerprint and ed25519_fingerprint
        }
    }
    charm = _make_charm(relation=relation)

    result = _get_ssh_debug_connections(charm)

    assert result == []


def test_ssh_debug_connections_sorted_by_host_port():
    """
    arrange: Two debug-ssh units with different hosts.
    act: Call _get_ssh_debug_connections().
    assert: Result is sorted by (host, port) for stable selection.
    """
    unit_a = MagicMock()
    unit_a.name = "tmate-ssh-server/0"
    unit_b = MagicMock()
    unit_b.name = "tmate-ssh-server/1"
    relation = MagicMock()
    relation.units = [unit_b, unit_a]  # intentionally reversed
    relation.data = {
        unit_a: {
            "host": "10.0.0.2",
            "port": "2222",
            "rsa_fingerprint": "SHA256:rsa-a",
            "ed25519_fingerprint": "SHA256:ed-a",
        },
        unit_b: {
            "host": "10.0.0.1",
            "port": "2222",
            "rsa_fingerprint": "SHA256:rsa-b",
            "ed25519_fingerprint": "SHA256:ed-b",
        },
    }
    charm = _make_charm(relation=relation)

    result = _get_ssh_debug_connections(charm)

    assert len(result) == 2
    assert result[0].host == "10.0.0.1"
    assert result[1].host == "10.0.0.2"


def test_charm_state_from_charm_no_debug_ssh_relation():
    """
    arrange: No debug-ssh relation exists.
    act: Call CharmState.from_charm().
    assert: ssh_debug_connections is empty.
    """
    charm = _make_charm(relation=None)
    state = CharmState.from_charm(charm)
    assert state.ssh_debug_connections == []


def test_charm_state_from_charm_with_debug_ssh_relation():
    """
    arrange: debug-ssh relation has one unit with complete data.
    act: Call CharmState.from_charm().
    assert: ssh_debug_connections contains one SSHDebugInfo entry.
    """
    unit = MagicMock()
    unit.name = "tmate-ssh-server/0"
    relation = MagicMock()
    relation.units = [unit]
    relation.data = {
        unit: {
            "host": "192.168.1.5",
            "port": "10022",
            "rsa_fingerprint": "SHA256:abc",
            "ed25519_fingerprint": "SHA256:def",
        }
    }
    charm = _make_charm(relation=relation)

    state = CharmState.from_charm(charm)

    assert len(state.ssh_debug_connections) == 1
    assert isinstance(state.ssh_debug_connections[0], SSHDebugInfo)
    assert state.ssh_debug_connections[0].host == "192.168.1.5"
