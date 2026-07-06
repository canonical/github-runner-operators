# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""State of the GARM configurator charm."""

import ops
from pydantic import (
    BaseModel,
    HttpUrl,
    IPvAnyNetwork,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

OPENSTACK_AUTH_URL_CONFIG_NAME = "openstack-auth-url"
OPENSTACK_USERNAME_CONFIG_NAME = "openstack-username"
OPENSTACK_PASSWORD_CONFIG_NAME = "openstack-password"  # nosec
OPENSTACK_PROJECT_NAME_CONFIG_NAME = "openstack-project-name"
OPENSTACK_USER_DOMAIN_NAME_CONFIG_NAME = "openstack-user-domain-name"
OPENSTACK_PROJECT_DOMAIN_NAME_CONFIG_NAME = "openstack-project-domain-name"
OPENSTACK_REGION_NAME_CONFIG_NAME = "openstack-region-name"
OPENSTACK_NETWORK_CONFIG_NAME = "openstack-network"

GITHUB_APP_ID_CONFIG_NAME = "github-app-id"
GITHUB_APP_INSTALLATION_ID_CONFIG_NAME = "github-app-installation-id"
GITHUB_APP_PRIVATE_KEY_CONFIG_NAME = "github-app-private-key"  # nosec

SCALESET_NAME_CONFIG_NAME = "name"
SCALESET_FLAVOR_CONFIG_NAME = "flavor"
SCALESET_OS_ARCH_CONFIG_NAME = "os-arch"
SCALESET_MIN_IDLE_RUNNER_CONFIG_NAME = "min-idle-runner"
SCALESET_MAX_RUNNER_CONFIG_NAME = "max-runner"
SCALESET_LABELS_CONFIG_NAME = "labels"
SCALESET_REPO_CONFIG_NAME = "repo"
SCALESET_ORG_CONFIG_NAME = "org"
SCALESET_RUNNER_GROUP_CONFIG_NAME = "runner-group"
SCALESET_PRE_INSTALL_SCRIPTS_CONFIG_NAME = "pre-install-scripts"

DOCKERHUB_MIRROR_CONFIG_NAME = "dockerhub-mirror"
RUNNER_HTTP_PROXY_CONFIG_NAME = "runner-http-proxy"
APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME = "aproxy-exclude-addresses"
APROXY_REDIRECT_PORTS_CONFIG_NAME = "aproxy-redirect-ports"
OTEL_COLLECTOR_ENDPOINT_CONFIG_NAME = "otel-collector-endpoint"
PRE_JOB_SCRIPT_CONFIG_NAME = "pre-job-script"

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_IP_NETWORK_ADAPTER = TypeAdapter(IPvAnyNetwork)

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
        app_id: GitHub App ID (numeric).
        installation_id: GitHub App installation ID.
        private_key: GitHub App private key (resolved from secret).
    """

    app_id: int
    installation_id: int
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
        app_id = charm.config.get(GITHUB_APP_ID_CONFIG_NAME)
        if app_id is None:
            raise CharmConfigInvalidError(
                f"Missing required configuration: {GITHUB_APP_ID_CONFIG_NAME}"
            )

        installation_id = charm.config.get(GITHUB_APP_INSTALLATION_ID_CONFIG_NAME)
        if installation_id is None:
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
            app_id=int(app_id),
            installation_id=int(installation_id),
            private_key=private_key,
        )


class ScalesetConfig(BaseModel):
    """Scaleset configuration.

    Attributes:
        name: The name of the scaleset.
        flavor: The resource flavor for runners.
        os_arch: The CPU architecture for runners.
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
        if max_runner <= 0:
            raise CharmConfigInvalidError(
                f"{SCALESET_MAX_RUNNER_CONFIG_NAME} must be greater than 0"
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
            min_idle_runner=min_idle_runner,
            max_runner=max_runner,
            labels=labels,
            repo=repo,
            org=org,
            runner_group=runner_group,
            pre_install_scripts=pre_install_scripts,
        )


class RunnerConfig(BaseModel):
    """Optional runner-level configuration forwarded to the GARM scaleset.

    Attributes:
        dockerhub_mirror: Optional Docker registry mirror URL.
        runner_http_proxy: HTTP proxy address for aproxy to forward to.
        aproxy_exclude_addresses: Comma-separated IPs/CIDRs excluded from aproxy forwarding.
        aproxy_redirect_ports: Comma-separated ports or N-M ranges forwarded to aproxy.
        otel_collector_endpoint: OTEL exporter address for the otel-collector.
        pre_job_script: Bash snippet appended to the runner pre-job script.
    """

    dockerhub_mirror: str | None = None
    runner_http_proxy: str | None = None
    aproxy_exclude_addresses: str | None = None
    aproxy_redirect_ports: str | None = None
    otel_collector_endpoint: str | None = None
    pre_job_script: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _strip_to_none(cls, data: object) -> object:
        """Strip whitespace and treat empty/whitespace-only values as unset."""
        if not isinstance(data, dict):
            return data
        return {
            key: (str(value).strip() or None) if value is not None else None
            for key, value in data.items()
        }

    @field_validator("dockerhub_mirror", "runner_http_proxy", "otel_collector_endpoint")
    @classmethod
    def _validate_http_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Require a set option to be a well-formed http(s) URL."""
        if value is None:
            return None
        # Field names are the snake_case form of the kebab-case config option.
        msg = f"{(info.field_name or '').replace('_', '-')} must be a valid http(s) URL"
        # Reject whitespace: the value is rendered into scripts and env files,
        # where a newline could inject extra lines.
        if any(char.isspace() for char in value):
            raise ValueError(msg)
        try:
            parsed = _HTTP_URL_ADAPTER.validate_python(value)
        except ValidationError as exc:
            raise ValueError(msg) from exc
        if parsed.port == 0:
            raise ValueError(msg)
        return value

    @field_validator("aproxy_exclude_addresses")
    @classmethod
    def _validate_ipv4_list(cls, value: str | None) -> str | None:
        """Require a comma-separated list of IPv4 addresses/CIDRs; normalise spacing."""
        if value is None:
            return None
        tokens = [token.strip() for token in value.split(",")]
        for token in tokens:
            # The values are rendered into an nft IPv4 (table ip) ruleset, so a
            # hostname or IPv6 address would validate here but fail at runtime.
            try:
                network = _IP_NETWORK_ADAPTER.validate_python(token)
            except ValidationError as exc:
                raise ValueError(
                    f"{APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME} must be a comma-separated list "
                    f"of IPv4 addresses or CIDRs; got invalid token: {token!r}"
                ) from exc
            if network.version != 4:
                raise ValueError(
                    f"{APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME} only supports IPv4 addresses or "
                    f"CIDRs (the aproxy nft ruleset is IPv4-only); got: {token!r}"
                )
        return ",".join(tokens)

    @field_validator("aproxy_redirect_ports")
    @classmethod
    def _validate_port_list(cls, value: str | None) -> str | None:
        """Require a comma-separated list of ports or N-M ranges in 1..65535."""
        if value is None:
            return None
        msg = (
            f"{APROXY_REDIRECT_PORTS_CONFIG_NAME} must be a comma-separated list of "
            "ports or N-M ranges in 1..65535"
        )
        tokens = [token.strip() for token in value.split(",")]
        for token in tokens:
            bounds = token.split("-")
            if len(bounds) > 2:
                raise ValueError(msg)
            try:
                ports = [int(part) for part in bounds]
            except ValueError as exc:
                raise ValueError(msg) from exc
            if not all(1 <= port <= 65535 for port in ports) or ports != sorted(ports):
                raise ValueError(msg)
        return ",".join(tokens)

    @model_validator(mode="after")
    def _aproxy_requires_proxy(self) -> "RunnerConfig":
        """The aproxy options only take effect alongside a proxy.

        The runner template renders the aproxy block solely when runner-http-proxy
        is set, so reject these options on their own rather than letting them no-op.
        """
        if (self.aproxy_exclude_addresses or self.aproxy_redirect_ports) and (
            not self.runner_http_proxy
        ):
            raise ValueError(
                f"{APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME} and {APROXY_REDIRECT_PORTS_CONFIG_NAME} "
                f"require {RUNNER_HTTP_PROXY_CONFIG_NAME} to be set"
            )
        return self

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "RunnerConfig":
        """Build and validate the runner config from charm configuration.

        All options are optional; unset, empty, or whitespace-only values become None.

        Args:
            charm: The charm instance.

        Raises:
            CharmConfigInvalidError: If a set option fails validation.

        Returns:
            The parsed runner configuration.
        """

        def config_str(name: str) -> str | None:
            """Return a string config value, or None when unset."""
            value = charm.config.get(name)
            return None if value is None else str(value)

        try:
            return cls(
                dockerhub_mirror=config_str(DOCKERHUB_MIRROR_CONFIG_NAME),
                runner_http_proxy=config_str(RUNNER_HTTP_PROXY_CONFIG_NAME),
                aproxy_exclude_addresses=config_str(APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME),
                aproxy_redirect_ports=config_str(APROXY_REDIRECT_PORTS_CONFIG_NAME),
                otel_collector_endpoint=config_str(OTEL_COLLECTOR_ENDPOINT_CONFIG_NAME),
                pre_job_script=config_str(PRE_JOB_SCRIPT_CONFIG_NAME),
            )
        except ValidationError as exc:
            raise CharmConfigInvalidError(str(exc)) from exc


class CharmState:
    """The charm state.

    Attributes:
        provider_config: OpenStack provider configuration.
        github_app_config: GitHub App configuration.
        scaleset_config: Scaleset configuration.
        runner_config: Optional runner-level configuration.
        image_id: OpenStack image UUID received from the image builder relation, or None.
    """

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        github_app_config: GithubAppConfig,
        scaleset_config: ScalesetConfig,
        runner_config: RunnerConfig,
        image_id: str | None,
    ) -> None:
        """Initialize the charm state.

        Args:
            provider_config: The OpenStack provider configuration.
            github_app_config: The GitHub App configuration.
            scaleset_config: The scaleset configuration.
            runner_config: The optional runner configuration.
            image_id: The OpenStack image UUID from the image builder relation.
        """
        self.provider_config = provider_config
        self.github_app_config = github_app_config
        self.scaleset_config = scaleset_config
        self.runner_config = runner_config
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
        runner_config = RunnerConfig.from_charm(charm)
        image_id = _get_image_id_from_relation(charm)
        return cls(
            provider_config=provider_config,
            github_app_config=github_app_config,
            scaleset_config=scaleset_config,
            runner_config=runner_config,
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
