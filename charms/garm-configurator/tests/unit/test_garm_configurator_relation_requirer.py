# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scenario tests for the ``garm-configurator`` relation requirer."""

import json

import ops
import pytest
from garm_configurator_relation import (
    GARM_CONFIGURATOR_RELATION_NAME,
    ConfiguratorData,
    GarmConfiguratorRequirer,
)
from scenario import Context, Relation, State

_META = {
    "name": "requirer-test",
    "requires": {
        GARM_CONFIGURATOR_RELATION_NAME: {"interface": "garm_configurator_v0"},
        "custom-endpoint": {"interface": "garm_configurator_v0"},
    },
}


class _RequirerCharm(ops.CharmBase):
    """Minimal charm exposing the requirer for scenario tests."""

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self.requirer = GarmConfiguratorRequirer(self)


def _relation(
    relation_id: int = 1,
    app_name: str = "configurator",
    units: dict[int, dict[str, str]] | None = None,
) -> Relation:
    return Relation(
        endpoint=GARM_CONFIGURATOR_RELATION_NAME,
        id=relation_id,
        remote_app_name=app_name,
        remote_units_data=units or {0: {}},
    )


def _get_data(*relations: Relation) -> ConfiguratorData:
    ctx = Context(_RequirerCharm, meta=_META)
    state = State(relations=list(relations))
    with ctx(ctx.on.start(), state) as manager:
        return manager.charm.requirer.get_data()


def test_get_data_orders_relations_and_units():
    """
    arrange: Two relations whose relations and units are supplied out of order.
    act: Read the aggregated relation data.
    assert: Relations are ordered by id then unit name, so first-wins deduplication in the
        garm charm does not flip between reconcile hooks.
    """
    relation_b = _relation(
        relation_id=2,
        app_name="configurator-b",
        units={0: {"name": "scaleset-b"}},
    )
    relation_a = _relation(
        relation_id=1,
        app_name="configurator-a",
        units={
            1: {"name": "scaleset-a1"},
            0: {"name": "scaleset-a0"},
        },
    )

    data = _get_data(relation_b, relation_a)

    assert [(item.relation_id, item.unit_name) for item in data.relations] == [
        (1, "configurator-a/0"),
        (1, "configurator-a/1"),
        (2, "configurator-b/0"),
    ]
    assert [item.application_name for item in data.relations] == [
        "configurator-a",
        "configurator-a",
        "configurator-b",
    ]


def test_get_data_builds_provider_and_scaleset_from_one_databag():
    """
    arrange: A relation unit carrying both provider and scaleset fields.
    act: Read the aggregated relation data.
    assert: One entry carries a typed provider and scaleset, so GARM can render the provider
        config and build the scaleset from the same read.
    """
    relation = _relation(
        units={
            0: {
                "openstack_auth_url": json.dumps("https://ks.example.com:5000/v3"),
                "openstack_username": json.dumps("admin"),
                "github_app_id": json.dumps(99999),
                "github_installation_id": json.dumps(67890),
                "name": "my-scaleset",
                "provider_name": "configurator-0",
                "flavor": "m1.large",
                "os_arch": "amd64",
                "min_idle_runner": "2",
                "max_runner": "6",
                "labels": "lxd,ubuntu",
                "repo": "my-org/my-repo",
            }
        }
    )

    item = _get_data(relation).relations[0]

    assert item.relation_id == 1
    assert item.application_name == "configurator"
    assert item.unit_name == "configurator/0"
    assert item.provider.openstack_auth_url == "https://ks.example.com:5000/v3"
    assert item.provider.openstack_username == "admin"
    assert item.provider.github_app_id == 99999
    assert item.provider.github_installation_id == 67890
    assert item.scaleset.name == "my-scaleset"
    assert item.scaleset.flavor == "m1.large"
    assert item.scaleset.max_runner == "6"
    assert item.scaleset.labels == "lxd,ubuntu"
    assert item.scaleset.repo == "my-org/my-repo"


def test_get_data_keeps_units_that_have_not_published_their_provider():
    """
    arrange: A unit that has published its scaleset fields but not its provider payload yet.
    act: Read the aggregated relation data.
    assert: The unit is present with an empty provider, so GARM can read the scaleset without
        treating the half-written relation as a complete provider.
    """
    relation = _relation(units={0: {"name": "my-scaleset"}})

    data = _get_data(relation)

    assert data.relations[0].scaleset.name == "my-scaleset"
    assert data.relations[0].provider.openstack_auth_url is None


def test_get_data_returns_empty_aggregate_without_relations():
    """
    arrange: A charm with no garm-configurator relation.
    act: Read the aggregated relation data.
    assert: The aggregate is empty instead of raising, so the garm charm can reconcile before
        a configurator is integrated.
    """
    data = _get_data()

    assert data.is_empty


def test_get_data_reads_the_configured_relation_name():
    """
    arrange: A charm whose model holds relations on a custom endpoint name.
    act: Read the aggregated relation data through a requirer configured for that endpoint.
    assert: The custom relations are aggregated, so the requirer can follow an endpoint the
        charm renames without changing the relation contract.
    """
    ctx = Context(_RequirerCharm, meta=_META)
    relation = Relation(
        endpoint="custom-endpoint",
        remote_app_name="configurator",
        remote_units_data={0: {"name": "my-scaleset"}},
    )
    state = State(relations=[relation])
    with ctx(ctx.on.start(), state) as manager:
        requirer = GarmConfiguratorRequirer(manager.charm, relation_name="custom-endpoint")
        data = requirer.get_data()

    assert data.relations[0].scaleset.name == "my-scaleset"


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
    ctx = Context(_RequirerCharm, meta=_META)
    state = State(relations=[_relation()] if related else [])
    with ctx(ctx.on.start(), state) as manager:
        assert manager.charm.requirer.is_related is expected
