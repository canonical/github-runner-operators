# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Models and requirer helpers for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm owns the relation contract and publishes one provider
configuration per unit with ``ops.Relation.save``. The models live with the charm so consumers
can share the same definitions and use ``ops.Relation.load`` instead of hand-writing databag
keys.

The ``GarmConfiguratorRequirer`` aggregates every joined ``garm-configurator`` relation into a
single ``ConfiguratorData`` value. The ``garm`` charm uses that value to render provider
configurations and build its scalesets.
"""

import dataclasses
import typing
from collections.abc import Iterable, Mapping

import ops
import pydantic

GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"

SCALESET_FIELDS: typing.Final = (
    "name",
    "provider_name",
    "image_id",
    "image_visibility",
    "security_group",
    "flavor",
    "os_arch",
    "min_idle_runner",
    "max_runner",
    "labels",
    "runner_group",
    "enable_shell",
    "pre_install_scripts",
    "org",
    "repo",
    "dockerhub_mirror",
    "runner_http_proxy",
    "aproxy_exclude_addresses",
    "aproxy_redirect_ports",
    "otel_collector_endpoint",
    "pre_job_script",
)


@pydantic.dataclasses.dataclass
class ProviderConfig:
    """Provider and GitHub App credentials published by one ``garm-configurator`` unit.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. Every field is optional because a unit publishes the provider
    payload only once its image and secrets are ready: until then the fields are absent from
    the databag rather than invalid.

    Attributes:
        openstack_auth_url: Keystone authentication URL.
        openstack_username: OpenStack username.
        openstack_password: Legacy plaintext password, or None when the secret URI is used.
        openstack_password_secret_uri: Juju secret URI holding the password.
        openstack_project_name: OpenStack project (tenant).
        openstack_user_domain_name: Domain of the user.
        openstack_project_domain_name: Domain of the project.
        openstack_region_name: OpenStack region.
        openstack_network: Network name or ID instances are attached to.
        github_app_id: GitHub App ID.
        github_installation_id: GitHub App installation ID.
        github_private_key_secret_uri: Juju secret URI holding the GitHub App private key.
    """

    openstack_auth_url: str | None = None
    openstack_username: str | None = None
    openstack_password: str | None = None
    openstack_password_secret_uri: str | None = None
    openstack_project_name: str | None = None
    openstack_user_domain_name: str | None = None
    openstack_project_domain_name: str | None = None
    openstack_region_name: str | None = None
    openstack_network: str | None = None
    github_app_id: int | None = None
    github_installation_id: int | None = None
    github_private_key_secret_uri: str | None = None


@dataclasses.dataclass(frozen=True)
class ScalesetConfig:
    """Scaleset fields published by one ``garm-configurator`` unit.

    The fields keep the relation's string wire form so the consumer applies its own parsing
    and validation. An empty string means "unset".

    Attributes:
        name: The name of the scaleset.
        provider_name: The GARM provider the scaleset runs on.
        image_id: Image name or ID used for runners.
        image_visibility: Glance visibility used for an image-name lookup.
        security_group: Security group attached to runner instances.
        flavor: Runner flavor.
        os_arch: Runner CPU architecture.
        min_idle_runner: Minimum number of idle runners.
        max_runner: Maximum number of runners.
        labels: Comma-separated runner labels.
        runner_group: Runner group for org registration.
        enable_shell: Whether GARM's remote shell is enabled, as a boolean string.
        pre_install_scripts: JSON object of pre-install script name to script body.
        org: Organization the runners register to.
        repo: Repository the runners register to.
        dockerhub_mirror: Docker registry mirror URL.
        runner_http_proxy: Upstream HTTP proxy for runners.
        aproxy_exclude_addresses: Comma-separated IPv4 addresses, CIDRs, or ranges to bypass.
        aproxy_redirect_ports: Comma-separated ports or port ranges to forward.
        otel_collector_endpoint: OTEL exporter endpoint.
        pre_job_script: Bash script appended to the runner pre-job hook.
    """

    name: str = ""
    provider_name: str = ""
    image_id: str = ""
    image_visibility: str = ""
    security_group: str = ""
    flavor: str = ""
    os_arch: str = ""
    min_idle_runner: str = ""
    max_runner: str = ""
    labels: str = ""
    runner_group: str = ""
    enable_shell: str = ""
    pre_install_scripts: str = ""
    org: str = ""
    repo: str = ""
    dockerhub_mirror: str = ""
    runner_http_proxy: str = ""
    aproxy_exclude_addresses: str = ""
    aproxy_redirect_ports: str = ""
    otel_collector_endpoint: str = ""
    pre_job_script: str = ""

    @classmethod
    def from_databag(cls, data: Mapping[str, str]) -> "ScalesetConfig":
        """Build a scaleset config from a relation unit databag.

        Args:
            data: The relation unit databag.

        Returns:
            The scaleset fields carried by the databag, with unset fields as empty strings.
        """
        return cls(**{name: data.get(name) or "" for name in SCALESET_FIELDS})


@dataclasses.dataclass(frozen=True)
class ConfiguratorRelation:
    """Relation data published by one ``garm-configurator`` unit.

    Attributes:
        relation_id: The Juju relation id, used to group units by application.
        application_name: The related configurator application's name.
        unit_name: The publishing unit's name.
        provider: The provider and GitHub App credentials the unit publishes.
        scaleset: The scaleset fields the unit publishes.
    """

    relation_id: int
    application_name: str
    unit_name: str
    provider: ProviderConfig
    scaleset: ScalesetConfig

    @property
    def provider_name(self) -> str:
        """Return the GARM provider name derived from the unit name.

        Returns:
            The unit name with ``/`` replaced by ``-``, matching GARM's provider registry.
        """
        return self.unit_name.replace("/", "-")


@dataclasses.dataclass(frozen=True)
class ConfiguratorData:
    """Every ``garm-configurator`` relation unit, aggregated for one reconcile pass.

    Attributes:
        relations: One entry per related unit, ordered by relation id then unit name.
    """

    relations: tuple[ConfiguratorRelation, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Whether no configurator unit is related.

        Returns:
            True when the aggregate holds no unit data.
        """
        return not self.relations


def get_providers_data(relations: Iterable[ops.Relation]) -> ConfiguratorData:
    """Aggregate all ``garm-configurator`` relations into one dataclass.

    Relations and units are sorted so the result is stable across hooks: Juju exposes units
    as an unordered set, and consumers use first-wins deduplication over this data.

    Args:
        relations: The joined ``garm-configurator`` relations.

    Returns:
        The aggregated relation data, one entry per related unit.
    """
    aggregated: list[ConfiguratorRelation] = []
    for relation in sorted(relations, key=lambda item: item.id):
        application_name = relation.app.name if relation.app else ""
        for unit in sorted(relation.units, key=lambda item: item.name):
            data = relation.data[unit]
            aggregated.append(
                ConfiguratorRelation(
                    relation_id=relation.id,
                    application_name=application_name,
                    unit_name=unit.name,
                    provider=relation.load(ProviderConfig, unit),
                    scaleset=ScalesetConfig.from_databag(data),
                )
            )
    return ConfiguratorData(relations=tuple(aggregated))


class GarmConfiguratorRequirer:
    """Requirer side of the ``garm-configurator`` relation, used by the ``garm`` charm."""

    def __init__(
        self,
        charm: ops.CharmBase,
        relation_name: str = GARM_CONFIGURATOR_RELATION_NAME,
    ) -> None:
        """Initialize the requirer.

        Args:
            charm: The charm instance reading the relations.
            relation_name: The name of the relation endpoint.
        """
        self._charm = charm
        self._relation_name = relation_name

    @property
    def is_related(self) -> bool:
        """Whether at least one configurator relation is joined.

        Returns:
            True when the endpoint has any relation.
        """
        return bool(self._charm.model.relations.get(self._relation_name, []))

    def get_data(self) -> ConfiguratorData:
        """Aggregate every joined configurator relation into one dataclass.

        Returns:
            The relation data for every related unit, ordered deterministically.
        """
        relations = self._charm.model.relations.get(self._relation_name, [])
        return get_providers_data(relations)
