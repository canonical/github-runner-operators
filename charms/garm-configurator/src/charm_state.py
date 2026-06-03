# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""State of the GARM configurator charm."""

import ops
from pydantic import BaseModel

OPENSTACK_AUTH_URL_CONFIG_NAME = "openstack-auth-url"
OPENSTACK_USERNAME_CONFIG_NAME = "openstack-username"
OPENSTACK_PASSWORD_CONFIG_NAME = "openstack-password"  # nosec
OPENSTACK_PROJECT_NAME_CONFIG_NAME = "openstack-project-name"
OPENSTACK_USER_DOMAIN_NAME_CONFIG_NAME = "openstack-user-domain-name"
OPENSTACK_PROJECT_DOMAIN_NAME_CONFIG_NAME = "openstack-project-domain-name"
OPENSTACK_REGION_NAME_CONFIG_NAME = "openstack-region-name"
OPENSTACK_NETWORK_CONFIG_NAME = "openstack-network"

GITHUB_APP_CLIENT_ID_CONFIG_NAME = "github-app-client-id"
GITHUB_APP_INSTALLATION_ID_CONFIG_NAME = "github-app-installation-id"
GITHUB_APP_PRIVATE_KEY_CONFIG_NAME = "github-app-private-key"  # nosec


class CharmConfigInvalidError(Exception):
    """Raised when charm configuration is invalid.

    Attributes:
        msg: Explanation of the error.
    """

    def __init__(self, msg: str):
        """Initialize a new instance of the CharmConfigInvalidError exception.

        Args:
            msg: Explanation of the error.
        """
        super().__init__(msg)
        self.msg = msg


class ProviderConfig(BaseModel):
    """OpenStack provider configuration.

    Attributes:
        auth_url: OpenStack Keystone authentication URL.
        username: OpenStack username.
        password: OpenStack password (resolved from secret).
        project_name: OpenStack project name.
        user_domain_name: OpenStack user domain name.
        project_domain_name: OpenStack project domain name.
        region_name: OpenStack region name.
        network: OpenStack network name or ID.
    """

    auth_url: str
    username: str
    password: str
    project_name: str
    user_domain_name: str
    project_domain_name: str
    region_name: str
    network: str

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "ProviderConfig":
        """Initialize the provider config from charm.

        Args:
            charm: The charm instance.

        Raises:
            CharmConfigInvalidError: If any configuration is missing or invalid.

        Returns:
            The parsed provider configuration.
        """
        required_string_configs = (
            OPENSTACK_AUTH_URL_CONFIG_NAME,
            OPENSTACK_USERNAME_CONFIG_NAME,
            OPENSTACK_PROJECT_NAME_CONFIG_NAME,
            OPENSTACK_USER_DOMAIN_NAME_CONFIG_NAME,
            OPENSTACK_PROJECT_DOMAIN_NAME_CONFIG_NAME,
            OPENSTACK_REGION_NAME_CONFIG_NAME,
            OPENSTACK_NETWORK_CONFIG_NAME,
        )
        for key in required_string_configs:
            value = charm.config.get(key)
            if not value or not str(value).strip():
                raise CharmConfigInvalidError(f"Missing required configuration: {key}")

        auth_url = str(charm.config.get(OPENSTACK_AUTH_URL_CONFIG_NAME)).strip()
        if not auth_url.startswith(("http://", "https://")):
            raise CharmConfigInvalidError(
                f"{OPENSTACK_AUTH_URL_CONFIG_NAME} must start with http:// or https://"
            )

        password_secret_id = charm.config.get(OPENSTACK_PASSWORD_CONFIG_NAME)
        if not password_secret_id:
            raise CharmConfigInvalidError(
                f"Missing required configuration: {OPENSTACK_PASSWORD_CONFIG_NAME}"
            )
        try:
            secret = charm.model.get_secret(id=str(password_secret_id))
            password = secret.get_content()["value"]
        except (ops.SecretNotFoundError, KeyError) as e:
            raise CharmConfigInvalidError(
                f"{OPENSTACK_PASSWORD_CONFIG_NAME} secret is invalid or missing 'value' key"
            ) from e

        return cls(
            auth_url=auth_url,
            username=str(charm.config.get(OPENSTACK_USERNAME_CONFIG_NAME)),
            password=password,
            project_name=str(charm.config.get(OPENSTACK_PROJECT_NAME_CONFIG_NAME)),
            user_domain_name=str(charm.config.get(OPENSTACK_USER_DOMAIN_NAME_CONFIG_NAME)),
            project_domain_name=str(charm.config.get(OPENSTACK_PROJECT_DOMAIN_NAME_CONFIG_NAME)),
            region_name=str(charm.config.get(OPENSTACK_REGION_NAME_CONFIG_NAME)),
            network=str(charm.config.get(OPENSTACK_NETWORK_CONFIG_NAME)),
        )


class GithubAppConfig(BaseModel):
    """GitHub App configuration.

    Attributes:
        client_id: GitHub App client ID.
        installation_id: GitHub App installation ID.
        private_key: GitHub App private key (resolved from secret).
    """

    client_id: str
    installation_id: str
    private_key: str

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "GithubAppConfig":
        """Initialize the GitHub App config from charm.

        Args:
            charm: The charm instance.

        Raises:
            CharmConfigInvalidError: If any configuration is missing or invalid.

        Returns:
            The parsed GitHub App configuration.
        """
        client_id = charm.config.get(GITHUB_APP_CLIENT_ID_CONFIG_NAME)
        if not client_id or not str(client_id).strip():
            raise CharmConfigInvalidError(
                f"Missing required configuration: {GITHUB_APP_CLIENT_ID_CONFIG_NAME}"
            )

        installation_id = charm.config.get(GITHUB_APP_INSTALLATION_ID_CONFIG_NAME)
        if not installation_id or not str(installation_id).strip():
            raise CharmConfigInvalidError(
                f"Missing required configuration: {GITHUB_APP_INSTALLATION_ID_CONFIG_NAME}"
            )

        private_key_secret_id = charm.config.get(GITHUB_APP_PRIVATE_KEY_CONFIG_NAME)
        if not private_key_secret_id:
            raise CharmConfigInvalidError(
                f"Missing required configuration: {GITHUB_APP_PRIVATE_KEY_CONFIG_NAME}"
            )
        try:
            secret = charm.model.get_secret(id=str(private_key_secret_id))
            private_key = secret.get_content()["value"]
        except (ops.SecretNotFoundError, KeyError) as e:
            raise CharmConfigInvalidError(
                f"{GITHUB_APP_PRIVATE_KEY_CONFIG_NAME} secret is invalid or missing 'value' key"
            ) from e

        return cls(
            client_id=str(client_id),
            installation_id=str(installation_id),
            private_key=private_key,
        )


class CharmState:
    """The charm state.

    Attributes:
        provider_config: OpenStack provider configuration.
        github_app_config: GitHub App configuration.
    """

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        github_app_config: GithubAppConfig,
    ) -> None:
        """Initialize the charm state.

        Args:
            provider_config: The OpenStack provider configuration.
            github_app_config: The GitHub App configuration.
        """
        self.provider_config = provider_config
        self.github_app_config = github_app_config

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "CharmState":
        """Initialize the state from charm.

        Args:
            charm: The charm instance.

        Raises:
            CharmConfigInvalidError: If an invalid configuration was set.

        Returns:
            Current state of the charm.
        """
        provider_config = ProviderConfig.from_charm(charm)
        github_app_config = GithubAppConfig.from_charm(charm)
        return cls(
            provider_config=provider_config,
            github_app_config=github_app_config,
        )
