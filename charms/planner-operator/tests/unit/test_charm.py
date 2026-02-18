# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for RelationFlavorConfig parsing."""

from unittest.mock import Mock

import pytest

from charm import GithubRunnerPlannerCharm, JujuError, RelationFlavorConfig
from planner import Flavor


def test_from_relation_data_returns_none_when_flavor_unset():
    """
    arrange: Relation data with no flavor key.
    act: Parse the relation data.
    assert: None is returned.
    """
    assert RelationFlavorConfig.from_relation_data({}) is None


def test_from_relation_data_returns_none_when_flavor_empty():
    """
    arrange: Relation data with an empty flavor key.
    act: Parse the relation data.
    assert: None is returned.
    """
    assert RelationFlavorConfig.from_relation_data({"flavor": ""}) is None


def test_from_relation_data_uses_defaults():
    """
    arrange: Relation data with only the flavor name set.
    act: Parse the relation data.
    assert: All other fields use their defaults.
    """
    config = RelationFlavorConfig.from_relation_data({"flavor": "small"})

    assert config.name == "small"
    assert config.platform == "github"
    assert config.labels == ["self-hosted"]
    assert config.priority == 50
    assert config.minimum_pressure == 0


def test_from_relation_data_parses_all_fields():
    """
    arrange: Relation data with all fields set.
    act: Parse the relation data.
    assert: All fields are parsed correctly.
    """
    data = {
        "flavor": "large",
        "platform": "openstack",
        "labels": '["self-hosted", "linux", "x64"]',
        "priority": "50",
        "minimum-pressure": "10",
    }

    config = RelationFlavorConfig.from_relation_data(data)

    assert config.name == "large"
    assert config.platform == "github"
    assert config.labels == ["self-hosted", "linux", "x64"]
    assert config.priority == 50
    assert config.minimum_pressure == 10


def test_from_relation_data_parses_comma_separated_labels():
    """
    arrange: Relation data with comma-separated labels.
    act: Parse the relation data.
    assert: Labels are split correctly.
    """
    data = {"flavor": "small", "labels": "self-hosted, linux, x64"}

    config = RelationFlavorConfig.from_relation_data(data)

    assert config.labels == ["self-hosted", "linux", "x64"]


def test_from_relation_data_errors_on_invalid_priority():
    """
    arrange: Relation data with a non-integer priority.
    act: Parse the relation data.
    assert: JujuError is raised.
    """
    data = {"flavor": "small", "priority": "not-a-number"}

    with pytest.raises(JujuError, match="Invalid priority"):
        RelationFlavorConfig.from_relation_data(data)


def test_from_relation_data_errors_on_invalid_minimum_pressure():
    """
    arrange: Relation data with a non-integer minimum pressure.
    act: Parse the relation data.
    assert: JujuError is raised.
    """
    data = {"flavor": "small", "minimum-pressure": "bad"}

    with pytest.raises(JujuError, match="Invalid minimum-pressure"):
        RelationFlavorConfig.from_relation_data(data)


def test_sync_managed_flavors_skips_matching_flavor():
    """
    arrange: An existing flavor that matches the wanted config.
    act: Sync managed flavors.
    assert: The flavor is neither deleted nor recreated.
    """
    charm = GithubRunnerPlannerCharm.__new__(GithubRunnerPlannerCharm)
    client = Mock()
    client.list_flavors.return_value = [
        Flavor(
            name="small",
            platform="github",
            labels=["self-hosted"],
            priority=50,
            minimum_pressure=0,
            is_disabled=False,
        ),
    ]
    wanted = {
        "small": RelationFlavorConfig(
            name="small",
            platform="github",
            labels=["self-hosted"],
            priority=50,
            minimum_pressure=0,
        )
    }

    charm._sync_managed_flavors(client=client, wanted_flavors=wanted)

    client.delete_flavor.assert_not_called()
    client.create_flavor.assert_not_called()


def test_sync_managed_flavors_recreates_stale_flavor():
    """
    arrange: An existing flavor with different config than wanted.
    act: Sync managed flavors.
    assert: The stale flavor is deleted and recreated with the new config.
    """
    charm = GithubRunnerPlannerCharm.__new__(GithubRunnerPlannerCharm)
    client = Mock()
    client.list_flavors.return_value = [
        Flavor(
            name="small",
            platform="github",
            labels=["self-hosted"],
            priority=50,
            minimum_pressure=0,
            is_disabled=False,
        ),
    ]
    wanted = {
        "small": RelationFlavorConfig(
            name="small",
            platform="github",
            labels=["self-hosted", "x64"],
            priority=100,
            minimum_pressure=5,
        )
    }

    charm._sync_managed_flavors(client=client, wanted_flavors=wanted)

    client.delete_flavor.assert_called_once_with("small")
    client.create_flavor.assert_called_once_with(
        flavor_name="small",
        platform="github",
        labels=["self-hosted", "x64"],
        priority=100,
        minimum_pressure=5,
    )


def test_sync_managed_flavors_deletes_orphans():
    """
    arrange: An existing flavor with no matching wanted entry.
    act: Sync managed flavors.
    assert: The orphaned flavor is deleted.
    """
    charm = GithubRunnerPlannerCharm.__new__(GithubRunnerPlannerCharm)
    client = Mock()
    client.list_flavors.return_value = [
        Flavor(
            name="manual-debug",
            platform="github",
            labels=["debug"],
            priority=1,
            minimum_pressure=0,
            is_disabled=False,
        )
    ]

    charm._sync_managed_flavors(client=client, wanted_flavors={})

    client.delete_flavor.assert_called_once_with("manual-debug")
