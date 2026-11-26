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

_OPENSTACK_PROVIDER_VALUES = {
    "provider_type": "openstack",
    "openstack_auth_url": "https://ks.example.com:5000/v3",
    "openstack_username": "admin",
    "openstack_password_secret_uri": "secret:password",
    "openstack_project_name": "myproject",
    "openstack_user_domain_name": "Default",
    "openstack_project_domain_name": "Default",
    "openstack_region_name": "RegionOne",
    "openstack_network": "external-net",
}


def _openstack_provider(**overrides: object) -> ProviderConfig:
    """Return a valid OpenStack provider payload."""
    return ProviderConfig(**{**_OPENSTACK_PROVIDER_VALUES, **overrides})


def _relation(relation_id: int = 1, scaleset_name: str = "my-scaleset") -> ConfiguratorRelation:
    """Return a minimal valid configurator relation."""
    return ConfiguratorRelation(
        relation_id=relation_id,
        application_name=f"configurator-{relation_id}",
        unit_name=f"configurator-{relation_id}/0",
        provider=_openstack_provider(),
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
        provider=_openstack_provider(),
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


def test_provider_config_represents_lxd_without_openstack_credentials():
    """
    arrange: An LXD provider payload with certificate secret URIs and no OpenStack fields.
    act: Build the relation model.
    assert: The LXD fields are carried through and the missing OpenStack auth URL is allowed,
        so a configurator can publish an LXD provider.
    """
    provider = ProviderConfig(
        provider_type="lxd",
        lxd_api_url="https://lxd.example.com:8443",
        lxd_project_name="runners",
        lxd_secure_boot=True,
        lxd_client_certificate_secret_uri="secret:client-cert",
        lxd_client_key_secret_uri="secret:client-key",
    )

    assert provider.provider_type == "lxd"
    assert provider.openstack_auth_url is None
    assert provider.lxd_api_url == "https://lxd.example.com:8443"
    assert provider.lxd_secure_boot is True
    assert provider.lxd_client_certificate_secret_uri == "secret:client-cert"
    assert provider.lxd_client_key_secret_uri == "secret:client-key"


def test_provider_config_defaults_provider_type_to_openstack():
    """
    arrange: An OpenStack provider payload without a provider type.
    act: Build the relation model.
    assert: The provider type defaults to openstack, so a configurator that does not publish it
        keeps working with an upgraded consumer.
    """
    values = dict(_OPENSTACK_PROVIDER_VALUES)
    del values["provider_type"]

    provider = ProviderConfig(**values)

    assert provider.provider_type == "openstack"


def test_provider_config_rejects_unknown_provider_type():
    """
    arrange: A provider payload naming an unsupported provider type.
    act: Build the relation model.
    assert: Validation fails, so a typo cannot select an unintended provider.
    """
    with pytest.raises(ValueError, match="provider_type must be one of"):
        _openstack_provider(provider_type="aws")


@pytest.mark.parametrize(
    "missing_field",
    [
        "openstack_auth_url",
        "openstack_username",
        "openstack_project_name",
        "openstack_user_domain_name",
        "openstack_project_domain_name",
        "openstack_region_name",
        "openstack_network",
    ],
)
def test_provider_config_requires_openstack_fields(missing_field: str):
    """
    arrange: An OpenStack provider payload with one required field unset.
    act: Build the relation model.
    assert: Validation fails, so GARM never renders a provider from a partial databag.
    """
    values = {**_OPENSTACK_PROVIDER_VALUES, missing_field: None}

    with pytest.raises(ValueError, match="Missing required fields"):
        ProviderConfig(**values)


def test_provider_config_requires_lxd_fields():
    """
    arrange: An LXD provider payload missing the client key secret URI.
    act: Build the relation model.
    assert: Validation fails, because GARM cannot authenticate to LXD without it.
    """
    with pytest.raises(ValueError, match="Missing required fields"):
        ProviderConfig(
            provider_type="lxd",
            lxd_api_url="https://lxd.example.com:8443",
            lxd_client_certificate_secret_uri="secret:client-cert",
        )


def test_provider_config_lxd_rejects_openstack_fields():
    """
    arrange: An LXD provider payload that also carries an OpenStack field.
    act: Build the relation model.
    assert: Validation fails, so a payload cannot mix provider settings.
    """
    with pytest.raises(ValueError, match="Fields not allowed for provider_type lxd"):
        ProviderConfig(
            provider_type="lxd",
            lxd_api_url="https://lxd.example.com:8443",
            lxd_client_certificate_secret_uri="secret:client-cert",
            lxd_client_key_secret_uri="secret:client-key",
            openstack_auth_url="https://ks.example.com:5000/v3",
        )


def test_provider_config_openstack_rejects_lxd_fields():
    """
    arrange: An OpenStack provider payload that also carries an LXD field.
    act: Build the relation model.
    assert: Validation fails, so a payload cannot mix provider settings.
    """
    with pytest.raises(ValueError, match="Fields not allowed for provider_type openstack"):
        _openstack_provider(lxd_api_url="https://lxd.example.com:8443")
