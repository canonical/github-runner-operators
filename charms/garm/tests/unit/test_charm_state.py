# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the charm_state module."""

from unittest.mock import MagicMock

import pytest

from charm_state import (
    DEBUG_SSH_INTEGRATION_NAME,
    CharmState,
    GarmConfig,
    SSHDebugInfo,
    _get_ssh_debug_connections,
)


def _make_charm(*, relation=None, config=None):
    """Build a minimal mock charm."""
    charm = MagicMock()
    charm.model.get_relation.return_value = relation
    charm.config.get.side_effect = lambda key, default=None: (config or {}).get(key, default)
    return charm


def test_garm_config_from_charm_defaults():
    """
    arrange: Charm config has no explicit values set.
    act: Call GarmConfig.from_charm().
    assert: use_runner_proxy_for_tmate defaults to False.
    """
    charm = _make_charm()
    result = GarmConfig.from_charm(charm)
    assert result.use_runner_proxy_for_tmate is False


def test_garm_config_from_charm_custom_values():
    """
    arrange: Charm config has use-runner-proxy-for-tmate set to True.
    act: Call GarmConfig.from_charm().
    assert: use_runner_proxy_for_tmate is True.
    """
    charm = _make_charm(config={"use-runner-proxy-for-tmate": True})
    result = GarmConfig.from_charm(charm)
    assert result.use_runner_proxy_for_tmate is True


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
