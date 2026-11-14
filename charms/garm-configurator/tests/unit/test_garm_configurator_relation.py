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


@pytest.mark.parametrize(
    "databag, expected",
    [
        pytest.param(
            {"name": "my-scaleset", "max_runner": "6", "repo": "my-org/my-repo"},
            {"name": "my-scaleset", "max_runner": "6", "repo": "my-org/my-repo"},
            id="reads-set-fields",
        ),
        pytest.param(
            {"name": "my-scaleset"},
            {"name": "my-scaleset", "max_runner": "", "repo": "", "runner_group": ""},
            id="leaves-unset-fields-empty",
        ),
        pytest.param(
            {"name": "my-scaleset", "unknown": "ignored"},
            {"name": "my-scaleset"},
            id="ignores-unknown-fields",
        ),
    ],
)
def test_scaleset_config_from_databag(databag: dict[str, str], expected: dict[str, str]):
    """
    arrange: A relation unit databag with some scaleset fields set.
    act: Build the scaleset config.
    assert: Set fields are read verbatim, unset fields stay empty strings, and unknown fields
        are ignored, so the consumer can apply its own defaults.
    """
    scaleset = ScalesetConfig.from_databag(databag)

    for field, value in expected.items():
        assert getattr(scaleset, field) == value


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
        provider=ProviderConfig(),
        scaleset=ScalesetConfig(),
    )

    assert relation.provider_name == expected


def test_configurator_data_is_empty_without_relations():
    """
    arrange: An aggregate with no configurator relations.
    act: Read its emptiness.
    assert: It reports empty, so GARM can treat the absence of relations as a real empty
        state rather than a malformed payload.
    """
    assert ConfiguratorData().is_empty


def test_configurator_data_is_not_empty_with_a_relation():
    """
    arrange: An aggregate holding one configurator relation.
    act: Read its emptiness.
    assert: It reports non-empty, so GARM knows there is provider data to reconcile.
    """
    data = ConfiguratorData(
        relations=(
            ConfiguratorRelation(
                relation_id=1,
                application_name="configurator",
                unit_name="configurator/0",
                provider=ProviderConfig(),
                scaleset=ScalesetConfig(),
            ),
        )
    )

    assert not data.is_empty
