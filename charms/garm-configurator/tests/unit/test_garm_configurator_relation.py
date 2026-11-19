# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the ``garm-configurator`` relation dataclasses."""

from types import SimpleNamespace

import pytest
from garm_configurator_relation import (
    ConfiguratorData,
    ConfiguratorRelation,
    GarmConfiguratorRequirer,
    ProviderConfig,
    ScalesetConfig,
)


def _relation(relation_id: int = 1, scaleset_name: str = "my-scaleset") -> ConfiguratorRelation:
    """Return a minimal valid configurator relation."""
    return ConfiguratorRelation(
        relation_id=relation_id,
        application_name=f"configurator-{relation_id}",
        provider=ProviderConfig(
            openstack_auth_url="https://ks.example.com:5000/v3",
            provider_name=f"configurator-{relation_id}-0",
        ),
        scaleset=ScalesetConfig(name=scaleset_name),
    )


def test_configurator_relation_provider_name():
    """
    arrange: A configurator relation whose application databag carries a provider name.
    act: Read its provider name.
    assert: The name is the one the configurator published, matching GARM's provider registry
        and the provider name its scalesets reference.
    """
    relation = _relation(relation_id=3)

    assert relation.provider_name == "configurator-3-0"


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


class _FakeApp:
    """Minimal related application for exercising the requirer without a live model."""

    name = "configurator"


class _FakeRelation:
    """Relation whose application databag either holds a payload or is still empty."""

    id = 1

    def __init__(self, provider: ProviderConfig | None = None) -> None:
        self.app = _FakeApp()
        self.data = {self.app: {"published": "true"}} if provider is not None else {}
        self._provider = provider
        self.loaded_entity = None

    def load(self, cls, entity, *args, **kwargs):
        """Return the provider payload only; the scaleset view must be derived from it."""
        if cls is not ProviderConfig:
            raise AssertionError(f"unexpected databag load for {cls.__name__}")
        self.loaded_entity = entity
        return self._provider


def test_requirer_derives_scaleset_view_from_provider_payload():
    """
    arrange: A configurator relation whose application payload also carries the basic fields.
    act: Aggregate the relation data.
    assert: The payload is read from the application databag and the scaleset view carries the
        same basic fields without re-reading the databag, so the configurator's single save
        remains the source of truth.
    """
    provider = ProviderConfig(
        openstack_auth_url="https://ks.example.com:5000/v3",
        provider_name="configurator-0",
        name="my-scaleset",
        org="myorg",
        max_runner="6",
    )
    relation = _FakeRelation(provider)
    charm = SimpleNamespace(model=SimpleNamespace(relations={"garm-configurator": [relation]}))

    data = GarmConfiguratorRequirer(charm).get_data()

    assert relation.loaded_entity is relation.app
    assert len(data.relations) == 1
    assert data.relations[0].application_name == "configurator"
    assert data.relations[0].provider_name == "configurator-0"
    assert data.relations[0].scaleset.name == "my-scaleset"
    assert data.relations[0].scaleset.org == "myorg"
    assert data.relations[0].scaleset.max_runner == "6"


def test_requirer_ignores_relation_without_application_data():
    """
    arrange: A configurator relation whose leader has not published an application payload.
    act: Aggregate the relation data.
    assert: The relation is neither exposed nor marked invalid, so GARM waits for the first
        publish instead of blocking on an unfinished relation.
    """
    relation = _FakeRelation()
    charm = SimpleNamespace(model=SimpleNamespace(relations={"garm-configurator": [relation]}))

    data = GarmConfiguratorRequirer(charm).get_data()

    assert data.is_empty
    assert not data.has_invalid_relations
