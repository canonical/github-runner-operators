# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for RelationFlavorConfig parsing."""

import pytest

from charm import JujuError, RelationFlavorConfig


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
