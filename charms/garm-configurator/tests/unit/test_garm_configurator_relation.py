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
        provider=ProviderConfig(openstack_auth_url="https://ks.example.com:5000/v3"),
        scaleset=ScalesetConfig(name=scaleset_name),
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
    arrange: A configurator relation whose scaleset payload names a provider, or leaves it unset.
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


# The `garm` charm does not consume `GarmConfiguratorRequirer` yet. Cover its aggregation with
# scenario tests once it does; until then there is no real charm to exercise it through.
