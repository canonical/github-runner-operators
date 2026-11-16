# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the ``garm-configurator`` relation dataclasses."""

import pytest
from garm_configurator_relation import (
    ConfiguratorData,
    ConfiguratorRelation,
    ProviderConfig,
    ScalesetConfig,
)


def _relation(relation_id: int = 1, scaleset_name: str = "my-scaleset") -> ConfiguratorRelation:
    """Return a minimal valid configurator relation."""
    return ConfiguratorRelation(
        relation_id=relation_id,
        application_name=f"configurator-{relation_id}",
        unit_name=f"configurator-{relation_id}/0",
        provider=ProviderConfig(openstack_auth_url="https://ks.example.com:5000/v3"),
        scaleset=ScalesetConfig(name=scaleset_name),
    )


@pytest.mark.parametrize(
    "unit_name, expected",
    [
        pytest.param("configurator/0", "configurator-0", id="unit-name-with-slash"),
        pytest.param("configurator", "configurator", id="unit-name-without-slash"),
    ],
)
def test_configurator_relation_provider_name(unit_name: str, expected: str):
    """
    arrange: A configurator relation whose unit name may contain a slash.
    act: Read its provider name.
    assert: The slash becomes a dash, matching GARM's provider registry and the provider name
        its scalesets reference.
    """
    relation = ConfiguratorRelation(
        relation_id=1,
        application_name="configurator",
        unit_name=unit_name,
        provider=ProviderConfig(openstack_auth_url="https://ks.example.com:5000/v3"),
        scaleset=ScalesetConfig(),
    )

    assert relation.provider_name == expected


@pytest.mark.parametrize(
    "data, expected_empty, expected_invalid",
    [
        pytest.param(ConfiguratorData(), True, False, id="no-relations"),
        pytest.param(
            ConfiguratorData(relations=(_relation(),)),
            False,
            False,
            id="valid-relation",
        ),
        pytest.param(
            ConfiguratorData(invalid_relation_ids=frozenset({1})),
            False,
            True,
            id="only-invalid-relation",
        ),
    ],
)
def test_configurator_data_reports_empty_and_invalid_state(
    data: ConfiguratorData, expected_empty: bool, expected_invalid: bool
):
    """
    arrange: An aggregate with no, one valid, or only an invalid configurator relation.
    act: Read its emptiness and invalid-relation flag.
    assert: The flags distinguish an empty deployment from one that has valid data to
        reconcile and from one that must block on an incomplete relation.
    """
    assert data.is_empty is expected_empty
    assert data.has_invalid_relations is expected_invalid


def test_configurator_data_keeps_relations_with_distinct_scaleset_names():
    """
    arrange: Two relations publishing different scaleset names.
    act: Build the aggregate.
    assert: Both relations survive, so separate scalesets are not treated as a conflict.
    """
    data = ConfiguratorData(relations=(_relation(1, "scaleset-a"), _relation(2, "scaleset-b")))

    assert [relation.scaleset.name for relation in data.relations] == [
        "scaleset-a",
        "scaleset-b",
    ]
    assert data.invalid_relation_ids == frozenset()


def test_configurator_data_rejects_every_relation_sharing_a_scaleset_name():
    """
    arrange: Two relations publishing the same scaleset name.
    act: Build the aggregate.
    assert: Both relations are removed and their ids recorded as invalid, because a GARM
        scaleset name must identify exactly one scaleset and picking a winner by order would
        let the scaleset flip between reconcile hooks.
    """
    data = ConfiguratorData(relations=(_relation(1, "my-scaleset"), _relation(2, "my-scaleset")))

    assert data.relations == ()
    assert data.invalid_relation_ids == frozenset({1, 2})
    assert data.has_invalid_relations
    assert not data.is_empty


def test_configurator_data_ignores_unset_scaleset_names_when_detecting_conflicts():
    """
    arrange: Two relations whose scaleset fields are not published yet.
    act: Build the aggregate.
    assert: Neither is treated as a conflict, so an incomplete publish does not hide the
        relation before the configurator writes its scaleset name.
    """
    data = ConfiguratorData(relations=(_relation(1, ""), _relation(2, "")))

    assert [relation.relation_id for relation in data.relations] == [1, 2]
    assert data.invalid_relation_ids == frozenset()
