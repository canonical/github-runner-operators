# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Models and requirer helpers for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm owns the relation contract and publishes one provider
configuration per application with ``ops.Relation.save``. ``ProviderConfig`` carries the
provider and GitHub App credentials (JSON-encoded, the default) and ``ScalesetConfig`` carries
the scaleset and runner fields (saved with ``encoder=str`` so their raw-string wire form is
preserved). The models live with the charm so consumers can share the same definitions and use
``ops.Relation.load`` instead of hand-writing databag keys.

The payload lives on the application databag: the configurator's leader unit writes it once for
the whole application. The ``GarmConfiguratorRequirer`` aggregates every joined
``garm-configurator`` relation into a single ``ConfiguratorData`` value. The ``garm`` charm uses
that value to render provider configurations and build its scalesets. An application that has
not published a complete provider payload is invalid; its relation id is recorded in
``ConfiguratorData.invalid_relation_ids`` instead of being exposed as an empty provider.
Relations that publish the same scaleset name are also invalid: a scaleset name must identify
exactly one scaleset in GARM.
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
    """Provider and GitHub App credentials published by one ``garm-configurator`` application.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. The auth URL is required: an application publishes the rest of the
    provider payload alongside it, so a databag without it is incomplete and treated as invalid
    rather than as an empty provider.

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
    """Scaleset and runner fields published by one ``garm-configurator`` application.

    The configurator fills this model and saves it with ``encoder=str``, which keeps the
    relation's raw-string wire form so older consumers can still read it. The fields are also
    loaded directly with ``decoder=str`` on the consuming side. An empty string means "unset".

    These fields are published on the application databag by the configurator's leader unit, so
    every unit of a deployment sees one consistent payload.

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
    """Relation data published by one ``garm-configurator`` application.

    Attributes:
        relation_id: The Juju relation id.
        application_name: The related configurator application's name.
        provider: The provider and GitHub App credentials the application publishes.
        scaleset: The scaleset fields the application publishes.
    """

    relation_id: int
    application_name: str
    provider: ProviderConfig
    scaleset: ScalesetConfig

    @property
    def provider_name(self) -> str:
        """Return the GARM provider name published by the configurator.

        Returns:
            The provider name the configurator wrote to its application databag, matching
            GARM's provider registry and the name its scalesets reference.
        """
        return self.scaleset.provider_name


# A scaleset name identifies the scaleset; a provider can legitimately serve several scalesets,
# so provider_name is not part of the identity.
_SCALESET_UNIQUE_FIELDS: typing.Final = ("name",)


@dataclasses.dataclass(frozen=True)
class ConfiguratorData:
    """Every ``garm-configurator`` relation application, aggregated for one reconcile pass.

    The requirer builds this value: it only exposes relations it could load and marks every
    relation it rejected in ``invalid_relation_ids``.

    Attributes:
        relations: One valid entry per related application.
        invalid_relation_ids: Relation ids whose application databag is incomplete, malformed,
            or conflicts with another relation over a scaleset identity field.
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
        """Whether any relation is unusable.

        Returns:
            True when at least one relation id was recorded as incomplete, malformed, or
            conflicting.
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

        The configurator publishes its payload on the application databag, so each relation
        yields at most one entry. A relation whose application databag is still empty has not
        published yet and is skipped without being marked invalid. A databag that is populated
        but cannot be loaded is recorded as invalid, so the consumer never renders a half-written
        provider. Relations that publish the same scaleset name are also rejected and marked
        invalid, so the consumer sees the conflict instead of a winner chosen by iteration
        order.

        Returns:
            The valid relation data for every related application, plus the ids of invalid
            relations.
        """
        aggregated: list[ConfiguratorRelation] = []
        invalid_relation_ids: set[int] = set()
        relations_by_identity: dict[tuple[str, ...], list[ConfiguratorRelation]] = {}
        relations = self._charm.model.relations.get(self._relation_name, [])
        for relation in relations:
            application = relation.app
            if application is None:
                invalid_relation_ids.add(relation.id)
                continue
            if not relation.data.get(application):
                logger.info(
                    "Ignoring garm-configurator relation with no application data yet: "
                    "relation_id=%d app=%s",
                    relation.id,
                    application.name,
                )
                continue
            try:
                provider = relation.load(ProviderConfig, application)
                scaleset = relation.load(ScalesetConfig, application, decoder=str)
            except ValueError:
                logger.warning(
                    "Ignoring incomplete garm-configurator relation data: relation_id=%d app=%s",
                    relation.id,
                    application.name,
                )
                invalid_relation_ids.add(relation.id)
                continue
            configurator_relation = ConfiguratorRelation(
                relation_id=relation.id,
                application_name=application.name,
                provider=provider,
                scaleset=scaleset,
            )
            aggregated.append(configurator_relation)
            identity = tuple(
                getattr(configurator_relation.scaleset, field) for field in _SCALESET_UNIQUE_FIELDS
            )
            if any(identity):
                relations_by_identity.setdefault(identity, []).append(configurator_relation)
        conflicting_ids = {
            relation.relation_id
            for group in relations_by_identity.values()
            if len(group) > 1
            for relation in group
        }
        if conflicting_ids:
            logger.warning(
                "Ignoring garm-configurator relations with conflicting scaleset %s: "
                "relation_ids=%s",
                "/".join(_SCALESET_UNIQUE_FIELDS),
                sorted(conflicting_ids),
            )
            aggregated = [
                relation for relation in aggregated if relation.relation_id not in conflicting_ids
            ]
            invalid_relation_ids |= conflicting_ids
        return ConfiguratorData(
            relations=tuple(aggregated),
            invalid_relation_ids=frozenset(invalid_relation_ids),
        )
