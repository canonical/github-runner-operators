# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for charm_state.py."""

from unittest.mock import MagicMock

import pytest

from charm_state import CharmState, RunnerConfig, SSHDebugInfo, _get_ssh_debug_connections

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


def _charm(units_data):
    """Build a mock charm whose configurator relation exposes the given unit databags.

    Units carry real, ordered names so the reconciler's stable-sort tie-break is exercised.
    """
    charm = MagicMock()
    relation = MagicMock()
    relation.id = 0
    data_map = {}
    for i, unit_data in enumerate(units_data):
        unit = MagicMock()
        unit.name = f"garm-configurator/{i}"
        data_map[unit] = unit_data
    relation.units = list(data_map)
    relation.data = data_map
    charm.model.relations.get.return_value = [relation]
    return charm


def _entities(units_data):
    return CharmState.from_charm(_charm(units_data)).desired_entities


@pytest.mark.parametrize(
    "unit_data, expected_type, expected_name",
    [
        (
            {"org": "canonical", "github_app_id": "12345", "github_installation_id": "67890"},
            "organization",
            "canonical",
        ),
        (
            {"repo": "canonical/runner", "github_app_id": "1", "github_installation_id": "2"},
            "repository",
            "canonical/runner",
        ),
    ],
    ids=["org-entity", "repo-entity"],
)
def test_desired_entities_built_from_relation(unit_data, expected_type, expected_name):
    """
    arrange: A configurator relation exposing a unit naming an org or repo plus the GitHub App ids.
    act: Build CharmState.desired_entities.
    assert: One entity is built with the right type/name, bound to the app-<id>-<id> credential.
    """
    entities = _entities([unit_data])

    assert len(entities) == 1
    entity = entities[0]
    assert entity.entity_type == expected_type
    assert entity.entity_name == expected_name
    assert entity.credentials_name == "app-{}-{}".format(
        unit_data["github_app_id"], unit_data["github_installation_id"]
    )


def test_desired_entities_dedupe_by_name():
    """
    arrange: A configurator relation exposing two units naming the same org.
    act: Build CharmState.desired_entities.
    assert: The two units collapse to a single entity registration.
    """
    unit_data = {"org": "canonical", "github_app_id": "1", "github_installation_id": "2"}

    assert len(_entities([dict(unit_data), dict(unit_data)])) == 1


def test_desired_entities_keep_first_on_conflicting_credential():
    """
    arrange: Two configurator units name the same org but derive different credentials.
    act: Build CharmState.desired_entities.
    assert: A single entity is kept, bound to the first unit's credential.
    """
    entities = _entities(
        [
            {"org": "canonical", "github_app_id": "1", "github_installation_id": "2"},
            {"org": "canonical", "github_app_id": "9", "github_installation_id": "9"},
        ]
    )

    assert len(entities) == 1
    assert entities[0].credentials_name == "app-1-2"


def test_desired_entities_distinguish_org_and_repo_with_same_name():
    """
    arrange: A configurator relation exposing an org and a repo that share the same raw name.
    act: Build CharmState.desired_entities.
    assert: Two distinct entities are produced — dedup is by (type, name), not name alone, so the
        org and repo do not collide.
    """
    entities = _entities(
        [
            {"org": "shared", "github_app_id": "1", "github_installation_id": "2"},
            {"repo": "shared", "github_app_id": "1", "github_installation_id": "2"},
        ]
    )

    assert {(e.entity_type, e.entity_name) for e in entities} == {
        ("organization", "shared"),
        ("repository", "shared"),
    }


@pytest.mark.parametrize(
    "unit_data",
    [
        {"github_app_id": "1", "github_installation_id": "2"},
        {"org": "canonical", "github_installation_id": "2"},
        {"org": "canonical", "github_app_id": "x", "github_installation_id": "2"},
    ],
    ids=["no-org-or-repo", "missing-app-id", "non-numeric-id"],
)
def test_desired_entities_skip_incomplete_unit(unit_data):
    """
    arrange: A configurator unit lacking an entity name or valid GitHub App ids.
    act: Build CharmState.desired_entities.
    assert: No entity is built.
    """
    assert _entities([unit_data]) == []


def test_runner_config_from_databag_and_has_config():
    """
    arrange: Empty and populated runner-config databags.
    act: Build RunnerConfig instances from the databags and inspect has_config.
    assert: Known keys are mapped, unknown keys are ignored, and has_config reflects content.
    """
    empty = RunnerConfig.from_databag({})
    assert empty == RunnerConfig()
    assert not empty.has_config()

    populated = RunnerConfig.from_databag(
        {"dockerhub_mirror": " https://m.test ", "irrelevant": "x"}
    )
    assert populated.dockerhub_mirror == "https://m.test"
    assert populated.has_config()


def test_runner_config_from_databag_drops_malformed_port_and_address_tokens():
    """
    arrange: A databag with well-formed, malformed, out-of-range and IPv6 tokens.
    act: Build a RunnerConfig from the databag.
    assert: Only the well-formed, in-range IPv4 tokens survive.
    """
    config = RunnerConfig.from_databag(
        {
            "aproxy_redirect_ports": "80,not-a-port,8000-9000,99 rm,99999,443-80",
            "aproxy_exclude_addresses": "10.0.0.0/8,evil;,2001:db8::1",
        }
    )

    assert config.aproxy_redirect_ports == "80,8000-9000"
    assert config.aproxy_exclude_addresses == "10.0.0.0/8"


def test_runner_config_from_databag_strips_newlines_from_otel_endpoint():
    """
    arrange: A databag whose OTEL endpoint contains a newline and extra assignment text.
    act: Build a RunnerConfig from the databag.
    assert: The endpoint is flattened into a single line, preventing env-file line injection.
    """
    config = RunnerConfig.from_databag(
        {"otel_collector_endpoint": "http://o.test:4318\nMALICIOUS=1"}
    )

    assert config.otel_collector_endpoint == "http://o.test:4318MALICIOUS=1"


def test_runner_config_from_databag_strips_newlines_from_dockerhub_mirror():
    """
    arrange: A databag whose Docker mirror URL contains a newline and extra assignment text.
    act: Build a RunnerConfig from the databag.
    assert: The mirror value is flattened, preventing env-file line injection.
    """
    config = RunnerConfig.from_databag({"dockerhub_mirror": "https://m.test\nMALICIOUS=1"})

    assert config.dockerhub_mirror == "https://m.testMALICIOUS=1"


def test_runner_config_from_databag_preserves_multiline_pre_job_script():
    """
    arrange: A databag whose pre_job_script is legitimately multi-line.
    act: Build a RunnerConfig from the databag.
    assert: Newlines in pre_job_script are preserved (unlike the single-line env fields).
    """
    config = RunnerConfig.from_databag({"pre_job_script": "echo one\necho two"})

    assert config.pre_job_script == "echo one\necho two"
