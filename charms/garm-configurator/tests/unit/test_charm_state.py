# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for charm_state."""

from charm_state import CharmState, GithubAppConfig, ProviderConfig, ScalesetConfig


def test_provider_name_is_explicit_field():
    """ProviderConfig.provider_name is stored as-is from the caller."""
    state = CharmState(
        provider_config=ProviderConfig(
            auth_url="https://keystone.example.com:5000/v3",
            username="admin",
            password="s3cr3t",
            project_name="myproject",
            user_domain_name="Default",
            project_domain_name="Default",
            region_name="RegionOne",
            network="external-net",
            provider_name="garm-configurator-0",
        ),
        github_app_config=GithubAppConfig(
            client_id="12345",
            installation_id="67890",
            private_key="private-key",
        ),
        scaleset_config=ScalesetConfig(
            name="my-scaleset",
            flavor="m1.large",
            os_arch="amd64",
            min_idle_runner=0,
            max_runner=5,
            repo="myorg/myrepo",
        ),
        image_id=None,
    )

    assert state.provider_config.provider_name == "garm-configurator-0"
