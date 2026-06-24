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

SCALESET_NAME_CONFIG_NAME = "name"
SCALESET_FLAVOR_CONFIG_NAME = "flavor"
SCALESET_OS_ARCH_CONFIG_NAME = "os-arch"
SCALESET_OS_TYPE_CONFIG_NAME = "os-type"
SCALESET_MIN_IDLE_RUNNER_CONFIG_NAME = "min-idle-runner"
SCALESET_MAX_RUNNER_CONFIG_NAME = "max-runner"
SCALESET_LABELS_CONFIG_NAME = "labels"
SCALESET_REPO_CONFIG_NAME = "repo"
SCALESET_ORG_CONFIG_NAME = "org"
SCALESET_RUNNER_GROUP_CONFIG_NAME = "runner-group"
SCALESET_PRE_INSTALL_SCRIPTS_CONFIG_NAME = "pre-install-scripts"

IMAGE_RELATION_NAME = "image"
GARM_RELATION_NAME = "garm-configurator"


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
        provider_name: GARM provider name. Defaults to the Juju unit name with "/" replaced by "-".
    """

    auth_url: str
    username: str
    password: str
    project_name: str
    user_domain_name: str
    project_domain_name: str
    region_name: str
    network: str
    provider_name: str

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
            password = secret.get_content(refresh=True)["value"]
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
            provider_name=charm.unit.name.replace("/", "-"),
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
            private_key = secret.get_content(refresh=True)["value"]
        except (ops.SecretNotFoundError, KeyError) as e:
            raise CharmConfigInvalidError(
                f"{GITHUB_APP_PRIVATE_KEY_CONFIG_NAME} secret is invalid or missing 'value' key"
            ) from e

        return cls(
            client_id=str(client_id),
            installation_id=str(installation_id),
            private_key=private_key,
        )


class ScalesetConfig(BaseModel):
    """Scaleset configuration.

    Attributes:
        name: The name of the scaleset.
        flavor: The resource flavor for runners.
        os_arch: The CPU architecture for runners.
        os_type: The operating system type for runners (linux or windows).
        min_idle_runner: Minimum number of idle runners.
        max_runner: Maximum number of runners.
        labels: Comma-separated list of labels for runners.
        repo: Repository to register runners to.
        org: Organization to register runners to.
        runner_group: Runner group for org registration.
        pre_install_scripts: Script name to bash script pairs for pre-installation.
    """

    name: str
    flavor: str
    os_arch: str
    os_type: str = "linux"
    min_idle_runner: int
    max_runner: int
    labels: str = ""
    repo: str | None = None
    org: str | None = None
    runner_group: str = "Default"
    pre_install_scripts: str | None = None

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "ScalesetConfig":
        """Initialize the scaleset config from charm.

        Args:
            charm: The charm instance.

        Raises:
            CharmConfigInvalidError: If any configuration is missing or invalid.

        Returns:
            The parsed scaleset configuration.
        """
        required_string_configs = (
            SCALESET_NAME_CONFIG_NAME,
            SCALESET_FLAVOR_CONFIG_NAME,
            SCALESET_OS_ARCH_CONFIG_NAME,
        )
        for key in required_string_configs:
            value = charm.config.get(key)
            if not value or not str(value).strip():
                raise CharmConfigInvalidError(f"Missing required configuration: {key}")

        min_idle_runner = int(charm.config.get(SCALESET_MIN_IDLE_RUNNER_CONFIG_NAME, 0))
        if min_idle_runner < 0:
            raise CharmConfigInvalidError(
                f"{SCALESET_MIN_IDLE_RUNNER_CONFIG_NAME} must be non-negative"
            )

        max_runner = int(charm.config.get(SCALESET_MAX_RUNNER_CONFIG_NAME, 0))
        if max_runner < 0:
            raise CharmConfigInvalidError(
                f"{SCALESET_MAX_RUNNER_CONFIG_NAME} must be non-negative"
            )
        if max_runner < min_idle_runner:
            raise CharmConfigInvalidError(
                f"{SCALESET_MAX_RUNNER_CONFIG_NAME} must be greater than or equal to "
                f"{SCALESET_MIN_IDLE_RUNNER_CONFIG_NAME}"
            )

        repo = charm.config.get(SCALESET_REPO_CONFIG_NAME)
        repo = str(repo).strip() if repo else None
        org = charm.config.get(SCALESET_ORG_CONFIG_NAME)
        org = str(org).strip() if org else None
        runner_group = str(charm.config.get(SCALESET_RUNNER_GROUP_CONFIG_NAME, "Default")).strip()

        if repo and org:
            raise CharmConfigInvalidError(
                f"{SCALESET_REPO_CONFIG_NAME} and {SCALESET_ORG_CONFIG_NAME} "
                f"are mutually exclusive"
            )
        if not repo and not org:
            raise CharmConfigInvalidError(
                f"At least one of {SCALESET_REPO_CONFIG_NAME} or "
                f"{SCALESET_ORG_CONFIG_NAME} must be provided"
            )

        labels = charm.config.get(SCALESET_LABELS_CONFIG_NAME)
        labels = str(labels).strip() if labels else ""
        pre_install_scripts = charm.config.get(SCALESET_PRE_INSTALL_SCRIPTS_CONFIG_NAME)
        pre_install_scripts = str(pre_install_scripts) if pre_install_scripts else None

        return cls(
            name=str(charm.config.get(SCALESET_NAME_CONFIG_NAME)).strip(),
            flavor=str(charm.config.get(SCALESET_FLAVOR_CONFIG_NAME)).strip(),
            os_arch=str(charm.config.get(SCALESET_OS_ARCH_CONFIG_NAME)).strip(),
            os_type=str(charm.config.get(SCALESET_OS_TYPE_CONFIG_NAME, "linux")).strip(),
            min_idle_runner=min_idle_runner,
            max_runner=max_runner,
            labels=labels,
            repo=repo,
            org=org,
            runner_group=runner_group,
            pre_install_scripts=pre_install_scripts,
        )


class CharmState:
    """The charm state.

    Attributes:
        provider_config: OpenStack provider configuration.
        github_app_config: GitHub App configuration.
        scaleset_config: Scaleset configuration.
        image_id: OpenStack image UUID received from the image builder relation, or None.
    """

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        github_app_config: GithubAppConfig,
        scaleset_config: ScalesetConfig,
        image_id: str | None,
    ) -> None:
        """Initialize the charm state.

        Args:
            provider_config: The OpenStack provider configuration.
            github_app_config: The GitHub App configuration.
            scaleset_config: The scaleset configuration.
            image_id: The OpenStack image UUID from the image builder relation.
        """
        self.provider_config = provider_config
        self.github_app_config = github_app_config
        self.scaleset_config = scaleset_config
        self.image_id = image_id

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
        scaleset_config = ScalesetConfig.from_charm(charm)
        image_id = _get_image_id_from_relation(charm)
        return cls(
            provider_config=provider_config,
            github_app_config=github_app_config,
            scaleset_config=scaleset_config,
            image_id=image_id,
        )


def _get_image_id_from_relation(charm: ops.CharmBase) -> str | None:
    """Return the OpenStack image UUID from the image builder relation, if available.

    Args:
        charm: The charm instance.

    Returns:
        The image UUID string, or None if the relation is absent or no UUID has been set yet.
    """
    relation = charm.model.get_relation(IMAGE_RELATION_NAME)
    if relation is None:
        return None
    for unit in relation.units:
        image_id = relation.data[unit].get("id")
        if image_id:
            return image_id
    return None
