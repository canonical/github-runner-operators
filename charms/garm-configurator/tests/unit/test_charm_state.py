# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for charm state provider configuration and image resolution."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import ops
import pytest
from pydantic import ValidationError

from charm_state import CharmConfigInvalidError, CharmState, ProviderConfig, ProviderType


def _image_relation(image_id: str | None = None):
    """Build the smallest relation-shaped object needed by image resolution."""
    unit = "image-builder/0"
    return SimpleNamespace(
        units=(unit,),
        data={unit: {"id": image_id} if image_id is not None else {}},
    )


@pytest.mark.parametrize(
    ("image_configuration", "image_relation", "expected_image", "overrides_builder"),
    [
        pytest.param(None, None, None, False, id="no-image-source"),
        pytest.param("configured-image", None, "configured-image", False, id="configured-only"),
        pytest.param(
            None, _image_relation("related-image"), "related-image", False, id="relation-only"
        ),
        pytest.param(
            "configured-image",
            _image_relation("related-image"),
            "configured-image",
            True,
            id="configured-image-takes-precedence",
        ),
        pytest.param(
            "configured-image",
            _image_relation(),
            "configured-image",
            True,
            id="configured-image-does-not-wait-for-relation-data",
        ),
    ],
)
def test_image_properties_are_derived_from_source_state(
    image_configuration, image_relation, expected_image, overrides_builder
):
    """Resolve image state from configuration and the image-builder relation."""
    state = CharmState(
        provider_config=None,
        github_app_config=None,
        scaleset_config=None,
        runner_config=None,
        image_relation=image_relation,
        image_configuration=image_configuration,
    )

    assert state.image == expected_image
    assert state.image_overrides_builder is overrides_builder


_LXD_SECRETS = {
    "secret:client-cert": "client-certificate",
    "secret:client-key": "client-key",
    "secret:server-cert": "server-certificate",
}


def _make_charm(config: dict, secrets: dict[str, str] | None = None) -> MagicMock:
    """Build a minimal mock charm with the given config and secret contents."""
    charm = MagicMock()
    charm.config = config
    charm.unit.name = "garm-configurator/0"
    contents = secrets or {}

    def get_secret(*, id: str) -> MagicMock:
        secret = MagicMock()
        secret.get_content.return_value = {"value": contents[id]}
        return secret

    if contents:
        charm.model.get_secret.side_effect = get_secret
    else:
        charm.model.get_secret.side_effect = ops.SecretNotFoundError("not found")
    return charm


def _lxd_config(**overrides: object) -> dict:
    """Return a minimal valid LXD config."""
    config = {
        "provider-type": "lxd",
        "lxd-api-url": "https://lxd.example.com:8443",
        "lxd-client-certificate": "secret:client-cert",
        "lxd-client-key": "secret:client-key",
    }
    config.update(overrides)
    return config


def test_provider_config_rejects_unknown_provider_type():
    """
    arrange: A provider config with an unsupported provider type.
    act: Build the model.
    assert: Validation fails, so a typo cannot silently select a provider.
    """
    with pytest.raises(ValidationError, match="provider-type must be one of"):
        ProviderConfig(provider_type="aws", provider_name="garm-configurator-0")


def test_provider_config_lxd_defaults():
    """
    arrange: A minimal LXD provider config with only the required connection details.
    act: Build the model.
    assert: The LXD project defaults to the documented value and secure boot is off.
    """
    config = ProviderConfig(
        provider_type="lxd",
        provider_name="garm-configurator-0",
        lxd_api_url="https://lxd.example.com:8443",
        lxd_client_certificate="client-certificate",
        lxd_client_key="client-key",
    )

    assert config.provider_type == ProviderType.LXD
    assert config.lxd_project_name == "default"
    assert config.lxd_secure_boot is False


def test_provider_config_rejects_non_https_lxd_api_url():
    """
    arrange: An LXD provider config whose API URL uses plain HTTP.
    act: Build the model.
    assert: Validation fails, because LXD credentials must never travel in the clear.
    """
    with pytest.raises(
        ValidationError, match="lxd-api-url must be a valid https:// URL with a host and port"
    ):
        ProviderConfig(
            provider_type="lxd",
            provider_name="garm-configurator-0",
            lxd_api_url="http://lxd.example.com:8443",
            lxd_client_certificate="client-certificate",
            lxd_client_key="client-key",
        )


@pytest.mark.parametrize(
    "api_url",
    [
        pytest.param("https://", id="missing-host"),
        pytest.param("https://:8443", id="port-without-host"),
        pytest.param("https://example.com:invalid", id="non-numeric-port"),
        pytest.param("https://example.com:0", id="zero-port"),
        pytest.param("https://example.com:70000", id="port-out-of-range"),
    ],
)
def test_provider_config_rejects_malformed_lxd_api_url(api_url: str):
    """
    arrange: An LXD provider config whose API URL has a malformed host or port.
    act: Build the model.
    assert: Validation fails, so an unusable endpoint is never published as Ready.
    """
    with pytest.raises(
        ValidationError, match="lxd-api-url must be a valid https:// URL with a host and port"
    ):
        ProviderConfig(
            provider_type="lxd",
            provider_name="garm-configurator-0",
            lxd_api_url=api_url,
            lxd_client_certificate="client-certificate",
            lxd_client_key="client-key",
        )


@pytest.mark.parametrize(
    "auth_url",
    [
        pytest.param("https://", id="missing-host"),
        pytest.param("https://:5000", id="port-without-host"),
        pytest.param("https://example.com:invalid", id="non-numeric-port"),
        pytest.param("ftp://keystone.example.com:5000/v3", id="unsupported-scheme"),
    ],
)
def test_provider_config_rejects_malformed_openstack_auth_url(auth_url: str):
    """
    arrange: An OpenStack provider config whose auth URL has a malformed host, port, or scheme.
    act: Build the model.
    assert: Validation fails, so an unusable Keystone endpoint is never published as Ready.
    """
    with pytest.raises(
        ValidationError,
        match="openstack-auth-url must be a valid http:// or https:// URL with a host and port",
    ):
        ProviderConfig(
            provider_type="openstack",
            provider_name="garm-configurator-0",
            auth_url=auth_url,
            username="admin",
            password="secret",
            project_name="myproject",
            user_domain_name="Default",
            project_domain_name="Default",
            region_name="RegionOne",
            network="external-net",
        )


@pytest.mark.parametrize(
    "openstack_field, value",
    [
        pytest.param("auth_url", "https://keystone.example.com:5000/v3", id="auth-url"),
        pytest.param("username", "admin", id="username"),
        pytest.param("project_name", "myproject", id="project-name"),
        pytest.param("user_domain_name", "Default", id="user-domain-name"),
        pytest.param("project_domain_name", "Default", id="project-domain-name"),
        pytest.param("region_name", "RegionOne", id="region-name"),
        pytest.param("network", "external-net", id="network"),
    ],
)
def test_provider_config_lxd_rejects_openstack_fields(openstack_field: str, value: str):
    """
    arrange: An LXD provider config that also sets one OpenStack-only field.
    act: Build the model.
    assert: Validation fails, so a unit cannot silently mix provider settings.
    """
    with pytest.raises(ValidationError, match="cannot be set when provider-type is lxd"):
        ProviderConfig(
            provider_type="lxd",
            provider_name="garm-configurator-0",
            lxd_api_url="https://lxd.example.com:8443",
            lxd_client_certificate="client-certificate",
            lxd_client_key="client-key",
            **{openstack_field: value},
        )


@pytest.mark.parametrize(
    "lxd_field, value",
    [
        pytest.param("lxd_api_url", "https://lxd.example.com:8443", id="api-url"),
        pytest.param("lxd_project_name", "runners", id="project-name"),
        pytest.param("lxd_secure_boot", True, id="secure-boot"),
        pytest.param("lxd_client_certificate", "client-certificate", id="client-certificate"),
        pytest.param("lxd_client_key", "client-key", id="client-key"),
        pytest.param("lxd_server_certificate", "server-certificate", id="server-certificate"),
    ],
)
def test_provider_config_openstack_rejects_lxd_fields(lxd_field: str, value: object):
    """
    arrange: An OpenStack provider config that also sets one LXD-only field.
    act: Build the model.
    assert: Validation fails, so a unit cannot silently mix provider settings.
    """
    values = {
        "provider_type": "openstack",
        "provider_name": "garm-configurator-0",
        "auth_url": "https://keystone.example.com:5000/v3",
        "username": "admin",
        "password": "secret",
        "project_name": "myproject",
        "user_domain_name": "Default",
        "project_domain_name": "Default",
        "region_name": "RegionOne",
        "network": "external-net",
        lxd_field: value,
    }

    with pytest.raises(ValidationError, match="cannot be set when provider-type is openstack"):
        ProviderConfig(**values)


@pytest.mark.parametrize(
    "missing_field",
    [
        "auth_url",
        "username",
        "password",
        "project_name",
        "user_domain_name",
        "project_domain_name",
        "region_name",
        "network",
    ],
    ids=[
        "auth-url",
        "username",
        "password",
        "project-name",
        "user-domain-name",
        "project-domain-name",
        "region-name",
        "network",
    ],
)
def test_provider_config_requires_openstack_fields(missing_field: str):
    """
    arrange: An OpenStack provider config with one required field left empty.
    act: Build the model.
    assert: Validation fails, because GARM cannot connect without it.
    """
    values = {
        "provider_type": "openstack",
        "provider_name": "garm-configurator-0",
        "auth_url": "https://keystone.example.com:5000/v3",
        "username": "admin",
        "password": "secret",
        "project_name": "myproject",
        "user_domain_name": "Default",
        "project_domain_name": "Default",
        "region_name": "RegionOne",
        "network": "external-net",
    }
    values[missing_field] = ""

    with pytest.raises(ValidationError, match="Missing required configuration"):
        ProviderConfig(**values)


@pytest.mark.parametrize(
    "missing_field",
    ["lxd_api_url", "lxd_client_certificate", "lxd_client_key"],
    ids=["api-url", "client-certificate", "client-key"],
)
def test_provider_config_requires_lxd_connection_details(missing_field: str):
    """
    arrange: An LXD provider config with one required connection detail left empty.
    act: Build the model.
    assert: Validation fails, because GARM cannot authenticate to LXD without it.
    """
    values = {
        "provider_type": "lxd",
        "provider_name": "garm-configurator-0",
        "lxd_api_url": "https://lxd.example.com:8443",
        "lxd_client_certificate": "client-certificate",
        "lxd_client_key": "client-key",
    }
    values[missing_field] = ""

    with pytest.raises(ValidationError, match="Missing required configuration"):
        ProviderConfig(**values)


def test_from_charm_lxd_resolves_secrets_and_defaults():
    """
    arrange: A valid LXD config whose certificates are operator secrets.
    act: Build the provider config from the charm.
    assert: The secret contents are resolved and optional values get their defaults, so the
        charm can publish credentials without requiring any OpenStack configuration.
    """
    charm = _make_charm(_lxd_config(), _LXD_SECRETS)

    config = ProviderConfig.from_charm(charm)

    assert config.provider_type == "lxd"
    assert config.lxd_api_url == "https://lxd.example.com:8443"
    assert config.lxd_client_certificate == "client-certificate"
    assert config.lxd_client_key == "client-key"
    assert config.lxd_server_certificate == ""
    assert config.lxd_project_name == "default"
    assert config.provider_name == "garm-configurator-0"


def test_from_charm_lxd_reads_project_and_secure_boot():
    """
    arrange: An LXD config that sets the optional project and secure boot.
    act: Build the provider config from the charm.
    assert: The configured values are carried through unchanged.
    """
    charm = _make_charm(
        _lxd_config(
            **{
                "lxd-project-name": "runners",
                "lxd-secure-boot": True,
                "lxd-server-certificate": "secret:server-cert",
            }
        ),
        _LXD_SECRETS,
    )

    config = ProviderConfig.from_charm(charm)

    assert config.lxd_project_name == "runners"
    assert config.lxd_secure_boot is True
    assert config.lxd_server_certificate == "server-certificate"


def test_from_charm_lxd_missing_secret_raises():
    """
    arrange: An LXD config whose client key option is unset.
    act: Build the provider config from the charm.
    assert: A CharmConfigInvalidError names the missing option, so the charm blocks clearly.
    """
    config = _lxd_config()
    del config["lxd-client-key"]
    charm = _make_charm(config, _LXD_SECRETS)

    with pytest.raises(
        CharmConfigInvalidError, match="Missing required configuration: lxd-client-key"
    ):
        ProviderConfig.from_charm(charm)


def test_from_charm_rejects_unknown_provider_type():
    """
    arrange: A config naming an unsupported provider type.
    act: Build the provider config from the charm.
    assert: A CharmConfigInvalidError is raised before any provider-specific parsing.
    """
    charm = _make_charm({"provider-type": "aws"})

    with pytest.raises(CharmConfigInvalidError, match="provider-type must be one of"):
        ProviderConfig.from_charm(charm)


def test_from_charm_lxd_invalid_api_url_raises_charm_error():
    """
    arrange: An LXD config whose API URL uses plain HTTP.
    act: Build the provider config from the charm.
    assert: The pydantic validation error is surfaced as a CharmConfigInvalidError so the
        unit blocks instead of publishing an insecure connection.
    """
    charm = _make_charm(
        _lxd_config(**{"lxd-api-url": "http://lxd.example.com:8443"}), _LXD_SECRETS
    )

    with pytest.raises(
        CharmConfigInvalidError,
        match="lxd-api-url must be a valid https:// URL with a host and port",
    ):
        ProviderConfig.from_charm(charm)


def test_from_charm_defaults_provider_type_to_openstack():
    """
    arrange: A complete OpenStack config that does not set provider-type.
    act: Build the provider config from the charm.
    assert: The provider type defaults to openstack, so existing deployments keep working
        without configuration changes.
    """
    config = {
        "openstack-auth-url": "https://keystone.example.com:5000/v3",
        "openstack-username": "admin",
        "openstack-password": "secret:password",
        "openstack-project-name": "myproject",
        "openstack-user-domain-name": "Default",
        "openstack-project-domain-name": "Default",
        "openstack-region-name": "RegionOne",
        "openstack-network": "external-net",
    }
    charm = _make_charm(config, {"secret:password": "password"})

    provider = ProviderConfig.from_charm(charm)

    assert provider.provider_type == ProviderType.OPENSTACK
