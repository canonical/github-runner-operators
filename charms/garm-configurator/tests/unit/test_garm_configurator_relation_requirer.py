# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Method-scoped unit tests for the ``garm-configurator`` relation requirer."""

import types
from unittest.mock import MagicMock

import ops
import pytest
from garm_configurator_relation import (
    GARM_CONFIGURATOR_RELATION_NAME,
    ConfiguratorData,
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


def test_get_data_aggregates_every_relation_unit():
    """
    arrange: Two relations, each publishing a provider and a scaleset.
    act: Read the aggregated relation data.
    assert: Every unit appears with its provider and scaleset, so GARM can render each
        configurator from one read.
    """
    provider_a = _provider("https://ks-a.example.com:5000/v3")
    provider_b = _provider("https://ks-b.example.com:5000/v3")
    relation_a = _relation(
        1,
        "configurator-a",
        {"configurator-a/0": (provider_a, ScalesetConfig(name="scaleset-a"), None)},
    )
    relation_b = _relation(
        2,
        "configurator-b",
        {"configurator-b/0": (provider_b, ScalesetConfig(name="scaleset-b"), None)},
    )

    data = GarmConfiguratorRequirer(_charm(relation_a, relation_b)).get_data()

    by_unit = {relation.unit_name: relation for relation in data.relations}
    assert set(by_unit) == {"configurator-a/0", "configurator-b/0"}
    assert by_unit["configurator-a/0"].application_name == "configurator-a"
    assert by_unit["configurator-a/0"].provider == provider_a
    assert by_unit["configurator-a/0"].scaleset.name == "scaleset-a"
    assert by_unit["configurator-b/0"].provider == provider_b
    assert by_unit["configurator-b/0"].scaleset.name == "scaleset-b"


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ValueError("missing provider payload"), id="incomplete-databag"),
        pytest.param(ValueError("not json"), id="malformed-encoding"),
    ],
)
def test_get_data_tracks_unreadable_relation_as_invalid(error: Exception):
    """
    arrange: A unit whose provider payload raises while loading, plus a valid unit.
    act: Read the aggregated relation data.
    assert: The unreadable relation is excluded and its id marked invalid, while the readable
        one survives, so GARM blocks on the broken configurator without dropping the rest.
    """
    broken = _relation(1, "configurator-broken", {"broken/0": (None, None, error)})
    valid = _relation(
        2,
        "configurator-valid",
        {"valid/0": (_provider(), ScalesetConfig(name="scaleset"), None)},
    )

    data = GarmConfiguratorRequirer(_charm(broken, valid)).get_data()

    assert [relation.unit_name for relation in data.relations] == ["valid/0"]
    assert data.invalid_relation_ids == frozenset({1})
    assert data.has_invalid_relations


def test_get_data_marks_every_relation_with_a_conflicting_scaleset_name_invalid():
    """
    arrange: Two relations publishing the same scaleset name.
    act: Read the aggregated relation data.
    assert: Neither relation is exposed and both ids are invalid, so GARM blocks on the
        conflict rather than letting iteration order pick which scaleset to own.
    """
    first = _relation(
        1,
        "configurator-a",
        {"configurator-a/0": (_provider(), ScalesetConfig(name="my-scaleset"), None)},
    )
    second = _relation(
        2,
        "configurator-b",
        {"configurator-b/0": (_provider(), ScalesetConfig(name="my-scaleset"), None)},
    )

    data = GarmConfiguratorRequirer(_charm(first, second)).get_data()

    assert data.relations == ()
    assert data.invalid_relation_ids == frozenset({1, 2})
    assert data.has_invalid_relations


def test_get_data_returns_empty_aggregate_without_relations():
    """
    arrange: A charm with no garm-configurator relation.
    act: Read the aggregated relation data.
    assert: The aggregate is empty instead of raising, so the garm charm can reconcile before
        a configurator is integrated.
    """
    data = GarmConfiguratorRequirer(_charm()).get_data()

    assert data == ConfiguratorData()
    assert data.is_empty
    assert not data.has_invalid_relations


def test_get_data_reads_the_configured_relation_name():
    """
    arrange: A charm whose model holds relations on a custom endpoint name.
    act: Read the aggregated relation data through a requirer configured for that endpoint.
    assert: The custom relations are aggregated, so the requirer can follow an endpoint the
        charm renames without changing the relation contract.
    """
    relation = _relation(
        1,
        "configurator",
        {"configurator/0": (_provider(), ScalesetConfig(name="my-scaleset"), None)},
    )
    charm = _charm(relation, relation_name="custom-endpoint")

    data = GarmConfiguratorRequirer(charm, relation_name="custom-endpoint").get_data()

    assert [item.scaleset.name for item in data.relations] == ["my-scaleset"]


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
