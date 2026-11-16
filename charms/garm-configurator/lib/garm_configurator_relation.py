# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Models and requirer helpers for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm owns the relation contract and publishes one provider
configuration per unit with ``ops.Relation.save``. The models live with the charm so consumers
can share the same definitions and use ``ops.Relation.load`` instead of hand-writing databag
keys.

The ``GarmConfiguratorRequirer`` aggregates every joined ``garm-configurator`` relation into a
single ``ConfiguratorData`` value. The ``garm`` charm uses that value to render provider
configurations and build its scalesets. A unit that has not published a complete provider
payload is invalid; its relation id is recorded in ``ConfiguratorData.invalid_relation_ids``
instead of being exposed as an empty provider.
"""

import dataclasses
import logging
import typing

import ops
import pydantic

logger = logging.getLogger(__name__)

GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"


@pydantic.dataclasses.dataclass
class ProviderConfig:
    """Provider and GitHub App credentials published by one ``garm-configurator`` unit.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. The auth URL is required: a unit publishes the rest of the provider
    payload alongside it, so a databag without it is incomplete and treated as invalid rather
    than as an empty provider.

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

    openstack_auth_url: str
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
        relations: One valid entry per related unit, ordered by relation id then unit name.
        invalid_relation_ids: Relation ids whose unit databag is incomplete or malformed.
    """

    relations: tuple[ConfiguratorRelation, ...] = ()
    invalid_relation_ids: frozenset[int] = frozenset()

    @property
    def is_empty(self) -> bool:
        """Whether no configurator relation data is present.

        Returns:
            True when the aggregate holds neither a valid relation nor an invalid relation id.
        """
        return not self.relations and not self.invalid_relation_ids

    @property
    def has_invalid_relations(self) -> bool:
        """Whether any relation published an incomplete or malformed databag.

        Returns:
            True when at least one relation id was recorded as invalid.
        """
        return bool(self.invalid_relation_ids)


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

        Relations and units are sorted so the result is stable across hooks: Juju exposes units
        as an unordered set, and consumers use first-wins deduplication over this data. A unit
        whose provider payload cannot be loaded is skipped and its relation id is recorded as
        invalid, so the consumer never renders a half-written provider.

        Returns:
            The valid relation data for every related unit, plus the ids of invalid relations.
        """
        aggregated: list[ConfiguratorRelation] = []
        invalid_relation_ids: set[int] = set()
        relations = self._charm.model.relations.get(self._relation_name, [])
        for relation in sorted(relations, key=lambda item: item.id):
            application_name = relation.app.name if relation.app else ""
            for unit in sorted(relation.units, key=lambda item: item.name):
                try:
                    provider = relation.load(ProviderConfig, unit)
                except ValueError:
                    logger.warning(
                        "Ignoring incomplete garm-configurator relation data: "
                        "relation_id=%d unit=%s",
                        relation.id,
                        unit.name,
                    )
                    invalid_relation_ids.add(relation.id)
                    continue
                aggregated.append(
                    ConfiguratorRelation(
                        relation_id=relation.id,
                        application_name=application_name,
                        unit_name=unit.name,
                        provider=provider,
                        scaleset=relation.load(ScalesetConfig, unit, decoder=str),
                    )
                )
        return ConfiguratorData(
            relations=tuple(aggregated),
            invalid_relation_ids=frozenset(invalid_relation_ids),
        )
