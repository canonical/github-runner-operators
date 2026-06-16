# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for charm_state."""

from charm_state import CharmState, GithubAppConfig, ProviderConfig, ScalesetConfig


def test_provider_name_derived_from_project_name():
    """CharmState.provider_name is openstack-{project_name}."""
    project_name = "myproject"
    state = CharmState(
        provider_config=ProviderConfig(
            auth_url="https://keystone.example.com:5000/v3",
            username="admin",
            password="s3cr3t",
            project_name=project_name,
            user_domain_name="Default",
            project_domain_name="Default",
            region_name="RegionOne",
            network="external-net",
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

    assert state.provider_name == f"openstack-{project_name}"


def test_credentials_name_derived_from_client_id():
    """CharmState.credentials_name is github-app-{client_id}."""
    client_id = "12345"
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
        ),
        github_app_config=GithubAppConfig(
            client_id=client_id,
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

    assert state.credentials_name == f"github-app-{client_id}"
