# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the ``garm-configurator`` relation dataclasses."""

import dataclasses
from types import SimpleNamespace

import pytest
from garm_configurator_relation import (
    ConfiguratorData,
    ConfiguratorRelation,
    GarmConfiguratorRequirer,
    ProviderConfig,
    ScalesetConfig,
    _decode_relation_value,
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


# The `garm` charm does not consume `GarmConfiguratorRequirer` yet. Cover its aggregation with
# scenario tests once it does; until then there is no real charm to exercise it through.


def test_provider_config_covers_every_scaleset_field():
    """
    arrange: The write model (ProviderConfig) and the read view (ScalesetConfig).
    act: Compare their field names.
    assert: Every scaleset field is on the write model, because the configurator publishes the
        whole payload with one save and the requirer derives the read view from it.
    """
    scaleset_fields = {field.name for field in dataclasses.fields(ScalesetConfig)}
    provider_fields = {field.name for field in dataclasses.fields(ProviderConfig)}

    assert scaleset_fields <= provider_fields


def test_provider_config_carries_basic_data():
    """
    arrange: A provider payload with scaleset and runner fields alongside credentials.
    act: Construct the write model.
    assert: The basic fields are part of the same dataclass, so one save publishes them all.
    """
    provider = ProviderConfig(
        openstack_auth_url="https://ks.example.com:5000/v3",
        name="my-scaleset",
        image_id="ubuntu:24.04",
        flavor="default",
        os_arch="amd64",
        min_idle_runner="2",
        max_runner="6",
        pre_job_script="echo start",
    )

    assert provider.name == "my-scaleset"
    assert provider.image_id == "ubuntu:24.04"
    assert provider.max_runner == "6"
    assert provider.pre_job_script == "echo start"


class _FakeUnit:
    """Minimal relation unit for exercising the requirer without a live model."""

    name = "configurator/0"


class _FakeRelation:
    """Relation that loads a known provider payload and rejects a second databag read."""

    id = 1
    application_name = "configurator"
    units = (_FakeUnit(),)

    def __init__(self, provider: ProviderConfig) -> None:
        self.app = SimpleNamespace(name=self.application_name)
        self._provider = provider

    def load(self, cls, unit, *args, **kwargs):
        """Return the provider payload only; the scaleset view must be derived from it."""
        if cls is not ProviderConfig:
            raise AssertionError(f"unexpected databag load for {cls.__name__}")
        return self._provider


def test_requirer_derives_scaleset_view_from_provider_payload():
    """
    arrange: A configurator relation whose provider payload also carries the basic fields.
    act: Aggregate the relation data.
    assert: The scaleset view carries the same basic fields without re-reading the databag, so
        the configurator's single save remains the source of truth.
    """
    provider = ProviderConfig(
        openstack_auth_url="https://ks.example.com:5000/v3",
        name="my-scaleset",
        org="myorg",
        max_runner="6",
    )
    charm = SimpleNamespace(
        model=SimpleNamespace(relations={"garm-configurator": [_FakeRelation(provider)]})
    )

    data = GarmConfiguratorRequirer(charm).get_data()

    assert len(data.relations) == 1
    assert data.relations[0].scaleset.name == "my-scaleset"
    assert data.relations[0].scaleset.org == "myorg"
    assert data.relations[0].scaleset.max_runner == "6"

@pytest.mark.parametrize(
    "raw, expected",
    [
        pytest.param('"my-scaleset"', "my-scaleset", id="json-string"),
        pytest.param("my-scaleset", "my-scaleset", id="legacy-raw-string"),
        pytest.param('""', "", id="json-empty-string"),
        pytest.param("null", None, id="json-null"),
        pytest.param("5", "5", id="json-number"),
    ],
)
def test_decode_relation_value_handles_old_and_new_wire_forms(raw, expected):
    """
    arrange: A databag value in either the JSON form written by Relation.save or the raw form
        written by an older configurator.
    act: Decode it for the provider model.
    assert: JSON strings and null decode, raw strings and numbers stay strings so a string
        field is not rejected while an integer field can still be coerced.
    """
    assert _decode_relation_value(raw) == expected

