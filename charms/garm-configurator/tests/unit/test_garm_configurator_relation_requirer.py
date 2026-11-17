# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Method-scoped unit tests for the ``garm-configurator`` relation requirer."""

import types
from unittest.mock import MagicMock

import ops
import pytest
from garm_configurator_relation import (
    GARM_CONFIGURATOR_RELATION_NAME,
    GarmConfiguratorRequirer,
    ProviderConfig,
    ScalesetConfig,
)


def _provider(auth_url: str = "https://ks.example.com:5000/v3") -> ProviderConfig:
    """Return a complete provider configuration."""
    return ProviderConfig(
        openstack_auth_url=auth_url,
        openstack_username="admin",
        openstack_project_name="myproject",
        github_app_id=99999,
        github_installation_id=67890,
    )


def _unit(name: str) -> MagicMock:
    """Return a relation unit mock carrying only the name the requirer reads."""
    unit = MagicMock(spec=ops.Unit)
    unit.name = name
    return unit


def _relation(
    relation_id: int,
    application_name: str,
    units: dict[str, tuple[ProviderConfig | None, ScalesetConfig | None, Exception | None]],
) -> MagicMock:
    """Return a relation mock whose ``load`` returns the given unit payloads."""
    relation = MagicMock(spec=ops.Relation)
    relation.id = relation_id
    relation.app = types.SimpleNamespace(name=application_name)
    payloads: dict[
        MagicMock, tuple[ProviderConfig | None, ScalesetConfig | None, Exception | None]
    ] = {}
    relation_units = []
    for unit_name, payload in units.items():
        unit = _unit(unit_name)
        relation_units.append(unit)
        payloads[unit] = payload
    relation.units = set(relation_units)

    def load(
        model: type[ProviderConfig] | type[ScalesetConfig],
        unit: MagicMock,
        decoder: type[str] | None = None,
    ) -> ProviderConfig | ScalesetConfig:
        provider, scaleset, error = payloads[unit]
        if error is not None:
            raise error
        if model is ProviderConfig:
            return provider
        return scaleset

    relation.load.side_effect = load
    return relation


def _charm(
    *relations: MagicMock, relation_name: str = GARM_CONFIGURATOR_RELATION_NAME
) -> MagicMock:
    """Return a charm mock exposing the given relations on one endpoint."""
    charm = MagicMock(spec=ops.CharmBase)
    charm.model.relations = {relation_name: list(relations)}
    return charm


def _relations_from_specs(
    specs: list[tuple[int, str, str, str | None, Exception | None]],
) -> list[MagicMock]:
    """Return one relation mock per (id, application, unit, scaleset name, load error) spec."""
    relations = []
    for relation_id, application_name, unit_name, scaleset_name, error in specs:
        if error is not None:
            payload = (None, None, error)
        else:
            payload = (_provider(), ScalesetConfig(name=scaleset_name or ""), None)
        relations.append(_relation(relation_id, application_name, {unit_name: payload}))
    return relations


@pytest.mark.parametrize(
    "specs, relation_name, expected_unit_names",
    [
        pytest.param(
            [
                (1, "configurator-a", "configurator-a/0", "scaleset-a", None),
                (2, "configurator-b", "configurator-b/0", "scaleset-b", None),
            ],
            GARM_CONFIGURATOR_RELATION_NAME,
            ["configurator-a/0", "configurator-b/0"],
            id="every-relation-unit",
        ),
        pytest.param(
            [
                (1, "configurator-a", "configurator-a/0", "", None),
                (2, "configurator-b", "configurator-b/0", "", None),
            ],
            GARM_CONFIGURATOR_RELATION_NAME,
            ["configurator-a/0", "configurator-b/0"],
            id="unset-scaleset-names",
        ),
        pytest.param([], GARM_CONFIGURATOR_RELATION_NAME, [], id="no-relations"),
        pytest.param(
            [(1, "configurator", "configurator/0", "my-scaleset", None)],
            "custom-endpoint",
            ["configurator/0"],
            id="custom-relation-name",
        ),
    ],
)
def test_get_data_aggregates_valid_relations(
    specs: list[tuple[int, str, str, str | None, Exception | None]],
    relation_name: str,
    expected_unit_names: list[str],
):
    """
    arrange: One or more relations publishing valid data, possibly on a custom endpoint, or no
        relation at all.
    act: Read the aggregated relation data.
    assert: Every relation unit keeps its provider, application, and scaleset; two relations
        may share an unset scaleset name without conflicting, and no relation yields an empty
        aggregate instead of raising, so GARM can render each configurator from one read.
    """
    data = GarmConfiguratorRequirer(
        _charm(*_relations_from_specs(specs), relation_name=relation_name),
        relation_name=relation_name,
    ).get_data()

    assert [relation.unit_name for relation in data.relations] == expected_unit_names
    assert {relation.unit_name: relation.application_name for relation in data.relations} == {
        unit_name: application_name for _, application_name, unit_name, _, _ in specs
    }
    assert {relation.unit_name: relation.scaleset.name for relation in data.relations} == {
        unit_name: scaleset_name or "" for _, _, unit_name, scaleset_name, _ in specs
    }
    assert all(relation.provider == _provider() for relation in data.relations)
    assert data.invalid_relation_ids == frozenset()
    assert data.is_empty is (not expected_unit_names)


@pytest.mark.parametrize(
    "specs, expected_unit_names, expected_invalid_ids",
    [
        pytest.param(
            [
                (
                    1,
                    "configurator-broken",
                    "broken/0",
                    None,
                    ValueError("missing provider payload"),
                ),
                (2, "configurator-valid", "valid/0", "scaleset", None),
            ],
            ["valid/0"],
            frozenset({1}),
            id="incomplete-databag",
        ),
        pytest.param(
            [
                (1, "configurator-broken", "broken/0", None, ValueError("not json")),
                (2, "configurator-valid", "valid/0", "scaleset", None),
            ],
            ["valid/0"],
            frozenset({1}),
            id="malformed-encoding",
        ),
        pytest.param(
            [
                (1, "configurator-a", "configurator-a/0", "my-scaleset", None),
                (2, "configurator-b", "configurator-b/0", "my-scaleset", None),
                (3, "configurator-c", "configurator-c/0", "other-scaleset", None),
            ],
            ["configurator-c/0"],
            frozenset({1, 2}),
            id="conflicting-scaleset-name",
        ),
    ],
)
def test_get_data_rejects_invalid_relations(
    specs: list[tuple[int, str, str, str | None, Exception | None]],
    expected_unit_names: list[str],
    expected_invalid_ids: frozenset[int],
):
    """
    arrange: A relation whose provider payload cannot be loaded, or relations publishing the
        same scaleset name, alongside valid relations.
    act: Read the aggregated relation data.
    assert: The invalid relations are excluded and their ids marked invalid while the valid
        relations survive, so GARM blocks on a broken configurator without dropping the rest
        and never lets iteration order pick which conflicting scaleset to own.
    """
    data = GarmConfiguratorRequirer(_charm(*_relations_from_specs(specs))).get_data()

    assert [relation.unit_name for relation in data.relations] == expected_unit_names
    assert {relation.unit_name: relation.scaleset.name for relation in data.relations} == {
        unit_name: scaleset_name or ""
        for _, _, unit_name, scaleset_name, _ in specs
        if unit_name in expected_unit_names
    }
    assert data.invalid_relation_ids == expected_invalid_ids
    assert data.has_invalid_relations


@pytest.mark.parametrize(
    "related, expected",
    [
        pytest.param(True, True, id="relation-joined"),
        pytest.param(False, False, id="no-relations"),
    ],
)
def test_is_related_reports_joined_relations(related: bool, expected: bool):
    """
    arrange: A charm with or without a garm-configurator relation.
    act: Check whether the requirer is related.
    assert: The result reflects the endpoint's relations, so event observers can gate on it.
    """
    relations = (
        [_relation(1, "configurator", {"configurator/0": (_provider(), ScalesetConfig(), None)})]
        if related
        else []
    )

    assert GarmConfiguratorRequirer(_charm(*relations)).is_related is expected


# The `garm` charm does not consume `GarmConfiguratorRequirer` yet. Add a scenario test using the
# real requirer there once it does; these method-scoped tests cover the aggregation itself.
