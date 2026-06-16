# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""State of the GARM configurator charm."""

import ipaddress
import urllib.parse

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

IMAGE_RELATION_NAME = "image"


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
    runner_group: str = "default"
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
        runner_group = str(charm.config.get(SCALESET_RUNNER_GROUP_CONFIG_NAME, "default")).strip()

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


def _validate_http_url(config_name: str, value: str) -> None:
    """Raise CharmConfigInvalidError if value is not a valid http(s) URL.

    Args:
        config_name: Config option name used in the error message.
        value: URL string to validate.

    Raises:
        CharmConfigInvalidError: When the URL has whitespace, a non-http(s) scheme,
            or an empty netloc.
    """
    # Reject embedded whitespace/control characters: the value is later rendered
    # into scripts and env files, where a newline could inject extra lines.
    if any(char.isspace() for char in value):
        raise CharmConfigInvalidError(f"{config_name} must be a valid http(s) URL")
    parsed = urllib.parse.urlparse(value)
    try:
        # Accessing .port raises ValueError on a non-numeric / out-of-range port,
        # which urlparse otherwise accepts silently.
        port = parsed.port
    except ValueError as exc:
        raise CharmConfigInvalidError(f"{config_name} must be a valid http(s) URL") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname or port == 0:
        raise CharmConfigInvalidError(f"{config_name} must be a valid http(s) URL")


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

    @classmethod
    def from_charm(cls, charm: ops.CharmBase) -> "RunnerConfig":
        """Initialize the runner config from charm, applying best-effort validation.

        All options are optional; unset or empty values result in None fields.

        Args:
            charm: The charm instance.

        Raises:
            CharmConfigInvalidError: If a set option fails validation.

        Returns:
            The parsed runner configuration.
        """
        url_options = (
            DOCKERHUB_MIRROR_CONFIG_NAME,
            RUNNER_HTTP_PROXY_CONFIG_NAME,
            OTEL_COLLECTOR_ENDPOINT_CONFIG_NAME,
        )
        url_values: dict[str, str | None] = {}
        for config_name in url_options:
            raw = charm.config.get(config_name)
            value = str(raw).strip() if raw else None
            if value:
                _validate_http_url(config_name, value)
            url_values[config_name] = value or None

        raw_exclude = charm.config.get(APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME)
        aproxy_exclude_addresses: str | None = None
        if raw_exclude:
            tokens = [t.strip() for t in str(raw_exclude).split(",")]
            # Reject empty tokens (e.g. trailing comma) as they signal a misconfiguration.
            for token in tokens:
                # Each token must be a valid IPv4 address or CIDR: the values are
                # rendered into an nft IPv4 (`table ip`) ruleset, so a hostname or
                # IPv6 address would pass validation but fail at runtime (and the
                # failure would be swallowed by ``|| true``).
                try:
                    network = ipaddress.ip_network(token, strict=False)
                except ValueError as exc:
                    raise CharmConfigInvalidError(
                        f"{APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME} must be a comma-separated list "
                        f"of IPv4 addresses or CIDRs; got invalid token: {token!r}"
                    ) from exc
                if network.version != 4:
                    raise CharmConfigInvalidError(
                        f"{APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME} only supports IPv4 addresses or "
                        f"CIDRs (the aproxy nft ruleset is IPv4-only); got: {token!r}"
                    )
            aproxy_exclude_addresses = ",".join(tokens)

        raw_ports = charm.config.get(APROXY_REDIRECT_PORTS_CONFIG_NAME)
        aproxy_redirect_ports: str | None = None
        if raw_ports:
            tokens_ports = [t.strip() for t in str(raw_ports).split(",")]
            for token in tokens_ports:
                _validate_port_token(token)
            aproxy_redirect_ports = ",".join(tokens_ports)

        # The aproxy options only take effect alongside a proxy: the runner
        # template renders the aproxy block solely when runner-http-proxy is set,
        # so reject these options on their own rather than letting them no-op.
        if (aproxy_exclude_addresses or aproxy_redirect_ports) and not url_values[
            RUNNER_HTTP_PROXY_CONFIG_NAME
        ]:
            raise CharmConfigInvalidError(
                f"{APROXY_EXCLUDE_ADDRESSES_CONFIG_NAME} and {APROXY_REDIRECT_PORTS_CONFIG_NAME} "
                f"require {RUNNER_HTTP_PROXY_CONFIG_NAME} to be set"
            )

        raw_script = charm.config.get(PRE_JOB_SCRIPT_CONFIG_NAME)
        pre_job_script = str(raw_script).strip() if raw_script else None

        return cls(
            dockerhub_mirror=url_values[DOCKERHUB_MIRROR_CONFIG_NAME],
            runner_http_proxy=url_values[RUNNER_HTTP_PROXY_CONFIG_NAME],
            aproxy_exclude_addresses=aproxy_exclude_addresses,
            aproxy_redirect_ports=aproxy_redirect_ports,
            otel_collector_endpoint=url_values[OTEL_COLLECTOR_ENDPOINT_CONFIG_NAME],
            pre_job_script=pre_job_script or None,
        )


def _validate_port_token(token: str) -> None:
    """Raise CharmConfigInvalidError if token is not a valid port or N-M range.

    Args:
        token: A single comma-split token from the aproxy-redirect-ports config.

    Raises:
        CharmConfigInvalidError: When the token is not a valid port or N<=M range in 1..65535.
    """
    error_msg = (
        f"{APROXY_REDIRECT_PORTS_CONFIG_NAME} must be a comma-separated list of "
        "ports or N-M ranges in 1..65535"
    )
    if "-" in token:
        parts = token.split("-", 1)
        try:
            low, high = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            raise CharmConfigInvalidError(error_msg)
        if not (1 <= low <= 65535 and 1 <= high <= 65535 and low <= high):
            raise CharmConfigInvalidError(error_msg)
    else:
        try:
            port = int(token)
        except ValueError:
            raise CharmConfigInvalidError(error_msg)
        if not 1 <= port <= 65535:
            raise CharmConfigInvalidError(error_msg)


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

    @property
    def provider_name(self) -> str:
        """Derived GARM provider name for scalesets."""
        return f"openstack-{self.provider_config.project_name}"

    @property
    def credentials_name(self) -> str:
        """Derived GARM credentials name for scalesets."""
        return f"github-app-{self.github_app_config.client_id}"


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
