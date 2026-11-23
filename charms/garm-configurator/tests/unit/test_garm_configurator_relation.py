# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the ``garm-configurator`` relation dataclasses."""

import dataclasses
from types import SimpleNamespace

import pytest
from garm_configurator_relation import (
    ConfiguratorApplicationData,
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
        ),
        scaleset=ScalesetConfig(
            name=scaleset_name,
            provider_name=f"configurator-{relation_id}-0",
        ),
    )


@pytest.mark.parametrize(
    "provider_name, expected",
    [
        pytest.param("configurator-0", "configurator-0", id="published-name"),
        pytest.param("", "", id="unset-name"),
    ],
)
def test_configurator_relation_provider_name(provider_name: str, expected: str):
    """
    arrange: A configurator relation whose scaleset value carries a provider name.
    act: Read its provider name.
    assert: The name published on the application databag is returned, matching GARM's provider
        registry and the provider name its scalesets reference.
    """
    relation = ConfiguratorRelation(
        relation_id=1,
        application_name="configurator",
        provider=ProviderConfig(openstack_auth_url="https://ks.example.com:5000/v3"),
        scaleset=ScalesetConfig(provider_name=provider_name),
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


def test_application_data_nests_provider_and_scaleset():
    """
    arrange: A complete configurator payload with provider credentials and scaleset fields.
    act: Serialise it the way ``ops.Relation.save`` does.
    assert: The databag has one ``provider`` object and one ``scaleset`` object, each holding
        only its own fields, so consumers parse the two concerns separately.
    """
    application_data = ConfiguratorApplicationData(
        provider=ProviderConfig(
            openstack_auth_url="https://ks.example.com:5000/v3",
            github_app_id=123,
        ),
        scaleset=ScalesetConfig(
            name="my-scaleset",
            provider_name="configurator-0",
            image_id="ubuntu:24.04",
            max_runner="6",
        ),
    )

    nested = dataclasses.asdict(application_data)

    assert set(nested) == {"provider", "scaleset"}
    assert nested["provider"] == {
        "openstack_auth_url": "https://ks.example.com:5000/v3",
        "openstack_username": None,
        "openstack_password": None,
        "openstack_password_secret_uri": None,
        "openstack_project_name": None,
        "openstack_user_domain_name": None,
        "openstack_project_domain_name": None,
        "openstack_region_name": None,
        "openstack_network": None,
        "github_app_id": 123,
        "github_installation_id": None,
        "github_private_key_secret_uri": None,
    }
    assert nested["scaleset"]["name"] == "my-scaleset"
    assert nested["scaleset"]["provider_name"] == "configurator-0"
    assert nested["scaleset"]["max_runner"] == "6"
    assert "name" not in nested["provider"]
    assert "openstack_auth_url" not in nested["scaleset"]


class _FakeApp:
    """Minimal related application for exercising the requirer without a live model."""

    name = "configurator"


class _FakeRelation:
    """Relation whose application databag either holds a payload or is still empty."""

    id = 1

    def __init__(self, application_data: ConfiguratorApplicationData | None = None) -> None:
        self.app = _FakeApp()
        self.data = {self.app: {"published": "true"}} if application_data is not None else {}
        self._application_data = application_data
        self.loaded_entity = None

    def load(self, cls, entity, *args, **kwargs):
        """Return the nested application payload loaded from the application databag."""
        if cls is not ConfiguratorApplicationData:
            raise AssertionError(f"unexpected databag load for {cls.__name__}")
        self.loaded_entity = entity
        return self._application_data


def test_requirer_reads_nested_provider_and_scaleset():
    """
    arrange: A configurator relation whose application databag holds nested provider and
        scaleset values.
    act: Aggregate the relation data.
    assert: The payload is read from the application databag and the relation exposes each
        nested value unchanged, so the configurator's single save remains the source of truth.
    """
    application_data = ConfiguratorApplicationData(
        provider=ProviderConfig(
            openstack_auth_url="https://ks.example.com:5000/v3",
            github_app_id=123,
        ),
        scaleset=ScalesetConfig(
            name="my-scaleset",
            provider_name="configurator-0",
            org="myorg",
            max_runner="6",
        ),
    )
    relation = _FakeRelation(application_data)
    charm = SimpleNamespace(model=SimpleNamespace(relations={"garm-configurator": [relation]}))

    data = GarmConfiguratorRequirer(charm).get_data()

    assert relation.loaded_entity is relation.app
    assert len(data.relations) == 1
    assert data.relations[0].application_name == "configurator"
    assert data.relations[0].provider_name == "configurator-0"
    assert data.relations[0].provider.openstack_auth_url == "https://ks.example.com:5000/v3"
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
