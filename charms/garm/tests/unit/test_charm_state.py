# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the charm_state module."""

from unittest.mock import MagicMock

import pytest

from charm_state import CharmState, SSHDebugInfo, _get_ssh_debug_connections

_COMPLETE = {
    "host": "10.0.0.1",
    "port": "2222",
    "rsa_fingerprint": "SHA256:rsa-fp",
    "ed25519_fingerprint": "SHA256:ed-fp",
}


def _make_charm(units_data=None):
    """Build a minimal mock charm.

    Args:
        units_data: ``None`` for no debug-ssh relation, otherwise a list of per-unit
            relation-data dicts (one mock remote unit is created per dict).

    Returns:
        A MagicMock charm whose ``model.get_relation`` returns the built relation.
    """
    charm = MagicMock()
    if units_data is None:
        charm.model.get_relation.return_value = None
        return charm

    relation = MagicMock()
    units = []
    data = {}
    for index, unit_data in enumerate(units_data):
        unit = MagicMock()
        unit.name = f"tmate-ssh-server/{index}"
        units.append(unit)
        data[unit] = unit_data
    relation.units = units
    relation.data = data
    charm.model.get_relation.return_value = relation
    return charm


@pytest.mark.parametrize(
    "units_data, expected",
    [
        pytest.param(None, [], id="no-relation"),
        pytest.param([], [], id="no-units"),
        pytest.param(
            [_COMPLETE],
            [("10.0.0.1", 2222, "SHA256:rsa-fp", "SHA256:ed-fp")],
            id="complete",
        ),
        pytest.param(
            [{"host": "10.0.0.1", "port": "2222"}],  # missing fingerprints
            [],
            id="missing-field",
        ),
        pytest.param(
            [{**_COMPLETE, "host": "10.0.0.1\nmalicious"}],
            [],
            id="newline-injection-rejected",
        ),
        pytest.param(
            [{**_COMPLETE, "rsa_fingerprint": "SHA256:rsa-fp\ninjected"}],
            [],
            id="newline-in-fingerprint-rejected",
        ),
        pytest.param(
            [{**_COMPLETE, "port": "not-an-int"}],
            [],
            id="invalid-port-rejected",
        ),
        pytest.param(
            [
                {**_COMPLETE, "host": "10.0.0.2", "rsa_fingerprint": "SHA256:rsa-a"},
                {**_COMPLETE, "host": "10.0.0.1", "rsa_fingerprint": "SHA256:rsa-b"},
            ],
            [
                ("10.0.0.1", 2222, "SHA256:rsa-b", "SHA256:ed-fp"),
                ("10.0.0.2", 2222, "SHA256:rsa-a", "SHA256:ed-fp"),
            ],
            id="two-units-sorted-by-host",
        ),
    ],
)
def test_get_ssh_debug_connections(units_data, expected):
    """
    arrange: A debug-ssh relation populated with the parametrized unit data.
    act: Call _get_ssh_debug_connections().
    assert: Only complete, injection-free, valid-port units survive, sorted by (host, port).
    """
    charm = _make_charm(units_data)

    result = _get_ssh_debug_connections(charm)

    assert [(c.host, c.port, c.rsa_fingerprint, c.ed25519_fingerprint) for c in result] == expected


def test_charm_state_from_charm_no_debug_ssh_relation():
    """
    arrange: No debug-ssh relation exists.
    act: Call CharmState.from_charm().
    assert: ssh_debug_connections is empty.
    """
    charm = _make_charm(None)
    state = CharmState.from_charm(charm)
    assert state.ssh_debug_connections == []


def test_charm_state_from_charm_with_debug_ssh_relation():
    """
    arrange: debug-ssh relation has one unit with complete data.
    act: Call CharmState.from_charm().
    assert: ssh_debug_connections contains one SSHDebugInfo with the unit's host.
    """
    charm = _make_charm(
        [
            {
                "host": "192.168.1.5",
                "port": "10022",
                "rsa_fingerprint": "SHA256:abc",
                "ed25519_fingerprint": "SHA256:def",
            }
        ]
    )

    state = CharmState.from_charm(charm)

    assert len(state.ssh_debug_connections) == 1
    assert isinstance(state.ssh_debug_connections[0], SSHDebugInfo)
    assert state.ssh_debug_connections[0].host == "192.168.1.5"
