# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for provider configuration parsing in charm_state.py."""

from unittest.mock import MagicMock

import ops
import pytest
from pydantic import ValidationError

from charm_state import CharmConfigInvalidError, ProviderConfig

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
    assert: The LXD project and instance type default to the documented values and secure
        boot is off.
    """
    config = ProviderConfig(
        provider_type="lxd",
        provider_name="garm-configurator-0",
        lxd_api_url="https://lxd.example.com:8443",
        lxd_client_certificate="client-certificate",
        lxd_client_key="client-key",
    )

    assert config.lxd_project_name == "default"
    assert config.lxd_instance_type == "virtual-machine"
    assert config.lxd_secure_boot is False


def test_provider_config_rejects_non_https_lxd_api_url():
    """
    arrange: An LXD provider config whose API URL uses plain HTTP.
    act: Build the model.
    assert: Validation fails, because LXD credentials must never travel in the clear.
    """
    with pytest.raises(ValidationError, match="lxd-api-url must start with https://"):
        ProviderConfig(
            provider_type="lxd",
            provider_name="garm-configurator-0",
            lxd_api_url="http://lxd.example.com:8443",
            lxd_client_certificate="client-certificate",
            lxd_client_key="client-key",
        )


def test_provider_config_rejects_unknown_lxd_instance_type():
    """
    arrange: An LXD provider config with an unsupported instance type.
    act: Build the model.
    assert: Validation fails, so only containers and virtual machines are accepted.
    """
    with pytest.raises(ValidationError, match="lxd-instance-type must be one of"):
        ProviderConfig(
            provider_type="lxd",
            provider_name="garm-configurator-0",
            lxd_api_url="https://lxd.example.com:8443",
            lxd_instance_type="vm",
            lxd_client_certificate="client-certificate",
            lxd_client_key="client-key",
        )


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
    assert config.lxd_instance_type == "virtual-machine"
    assert config.provider_name == "garm-configurator-0"


def test_from_charm_lxd_reads_project_instance_type_and_secure_boot():
    """
    arrange: An LXD config that sets the optional project, instance type, and secure boot.
    act: Build the provider config from the charm.
    assert: The configured values are carried through unchanged.
    """
    charm = _make_charm(
        _lxd_config(
            **{
                "lxd-project-name": "runners",
                "lxd-instance-type": "container",
                "lxd-secure-boot": True,
                "lxd-server-certificate": "secret:server-cert",
            }
        ),
        _LXD_SECRETS,
    )

    config = ProviderConfig.from_charm(charm)

    assert config.lxd_project_name == "runners"
    assert config.lxd_instance_type == "container"
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

    with pytest.raises(CharmConfigInvalidError, match="lxd-api-url must start with https://"):
        ProviderConfig.from_charm(charm)
