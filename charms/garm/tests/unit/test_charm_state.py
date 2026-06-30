# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for charm_state.py."""

from unittest.mock import MagicMock

import pytest

from charm_state import CharmState


def _charm(units_data):
    """Build a mock charm whose configurator relation exposes the given unit databags."""
    charm = MagicMock()
    relation = MagicMock()
    data_map = {}
    for unit_data in units_data:
        unit = MagicMock()
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
