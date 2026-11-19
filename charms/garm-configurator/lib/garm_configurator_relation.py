# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Models and requirer helpers for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm owns the relation contract and publishes one provider
configuration per application with ``ops.Relation.save``. The models live with the charm so
consumers can share the same definitions and use ``ops.Relation.load`` instead of hand-writing
databag keys. The application databag holds two nested values: ``provider`` (the provider and
GitHub App credentials) and ``scaleset`` (the scaleset and runner fields).
``ConfiguratorApplicationData`` is the write model that nests both, so the configurator writes
the complete payload with a single ``ops.Relation.save`` call.

The payload lives on the application databag: the configurator's leader unit writes it once for
the whole application. The ``GarmConfiguratorRequirer`` aggregates every joined
``garm-configurator`` relation into a single ``ConfiguratorData`` value. The ``garm`` charm uses
that value to render provider configurations and build its scalesets. An application that has
not published a complete provider payload is invalid; its relation id is recorded in
``ConfiguratorData.invalid_relation_ids`` instead of being exposed as an empty provider.
Relations that publish the same scaleset name are also invalid: a scaleset name must identify
exactly one scaleset in GARM.

The models distinguish the fields that block provider or scaleset creation (required, with no
default) from the fields GARM can default (optional, with the default shown on the field). A
payload missing a required field, or carrying a blank value for one, does not validate, so the
consumer never renders a provider or scaleset from a partial databag.
"""

import dataclasses
import logging
import typing

import ops
import pydantic

logger = logging.getLogger(__name__)


def _reject_blank(value: str, info: pydantic.ValidationInfo) -> str:
    """Reject a required string that is empty or whitespace-only.

    Args:
        value: The field value.
        info: Pydantic validation context.

    Raises:
        ValueError: If the value has no non-whitespace content.

    Returns:
        The unchanged value, so optional whitespace is preserved where it is meaningful.
    """
    if not value.strip():
        raise ValueError(f"{info.field_name} must not be empty")
    return value


GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"


@pydantic.dataclasses.dataclass
class ProviderConfig:
    """Provider and GitHub App credentials published by one ``garm-configurator`` application.

    This is the nested ``provider`` value of the application databag. The field names are the
    keys inside that value, so they are the wire contract between the configurator and GARM.

    The OpenStack credentials, the GitHub App ids, and the private-key secret URI are required:
    GARM cannot create a provider, credential, entity, or scaleset without them. A payload that
    omits one, or leaves it blank, is invalid. The password is required too, either inline for
    backwards compatibility or through the secret URI the configurator publishes.

    Attributes:
        openstack_auth_url: Keystone authentication URL.
        openstack_username: OpenStack username.
        openstack_project_name: OpenStack project (tenant).
        openstack_user_domain_name: Domain of the user.
        openstack_project_domain_name: Domain of the project.
        openstack_region_name: OpenStack region.
        openstack_network: Network name or ID instances are attached to.
        github_app_id: GitHub App ID.
        github_installation_id: GitHub App installation ID.
        github_private_key_secret_uri: Juju secret URI holding the GitHub App private key.
        openstack_password: Inline OpenStack password, superseded by the secret URI.
        openstack_password_secret_uri: Juju secret URI holding the OpenStack password.
    """

    openstack_auth_url: str
    openstack_username: str
    openstack_project_name: str
    openstack_user_domain_name: str
    openstack_project_domain_name: str
    openstack_region_name: str
    openstack_network: str
    github_app_id: int
    github_installation_id: int
    github_private_key_secret_uri: str
    openstack_password: str | None = None
    openstack_password_secret_uri: str | None = None

    _validate_required_strings = pydantic.field_validator(
        "openstack_auth_url",
        "openstack_username",
        "openstack_project_name",
        "openstack_user_domain_name",
        "openstack_project_domain_name",
        "openstack_region_name",
        "openstack_network",
        "github_private_key_secret_uri",
    )(_reject_blank)

    @pydantic.model_validator(mode="after")
    def _require_password_source(self) -> "ProviderConfig":
        """Require the password inline or through a secret URI.

        Raises:
            ValueError: If neither password source is published.

        Returns:
            The validated provider configuration.
        """
        if not (self.openstack_password or self.openstack_password_secret_uri):
            raise ValueError(
                "one of openstack_password or openstack_password_secret_uri is required"
            )
        return self


@pydantic.dataclasses.dataclass(frozen=True)
class ScalesetConfig:
    """Scaleset and runner fields published by one ``garm-configurator`` application.

    This is the nested ``scaleset`` value of the application databag. The requirer exposes it
    as-is, so consumers apply their own parsing and validation without re-reading the databag.
    The fields keep the relation's string wire form; an empty string means "unset".

    These fields are published on the application databag by the configurator's leader unit, so
    every unit of a deployment sees one consistent payload.

    A scaleset cannot be created without a name, provider, image, flavor, and architecture; those
    fields are required and must not be blank. It also needs an entity to register runners to,
    so exactly one of ``org`` or ``repo`` must be set. The remaining fields have the defaults
    shown on the field, because GARM or the configurator's own config supplies a sensible value
    when they are omitted.

    Attributes:
        name: The name of the scaleset.
        provider_name: The GARM provider the scaleset runs on.
        image_id: Image name or ID used for runners.
        flavor: Runner flavor.
        os_arch: Runner CPU architecture.
        image_visibility: Glance visibility used for an image-name lookup.
        security_group: Security group attached to runner instances.
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

    name: str
    provider_name: str
    image_id: str
    flavor: str
    os_arch: str
    image_visibility: str = ""
    security_group: str = ""
    min_idle_runner: str = "0"
    max_runner: str = "1"
    labels: str = ""
    runner_group: str = "Default"
    enable_shell: str = "false"
    pre_install_scripts: str = ""
    org: str = ""
    repo: str = ""
    dockerhub_mirror: str = ""
    runner_http_proxy: str = ""
    aproxy_exclude_addresses: str = ""
    aproxy_redirect_ports: str = ""
    otel_collector_endpoint: str = ""
    pre_job_script: str = ""

    _validate_required_strings = pydantic.field_validator(
        "name",
        "provider_name",
        "image_id",
        "flavor",
        "os_arch",
    )(_reject_blank)

    @pydantic.model_validator(mode="after")
    def _require_exactly_one_entity(self) -> "ScalesetConfig":
        """Require exactly one of the mutually exclusive entity fields.

        Raises:
            ValueError: If neither or both of ``org`` and ``repo`` are set.

        Returns:
            The validated scaleset configuration.
        """
        if bool(self.org) == bool(self.repo):
            raise ValueError("exactly one of org or repo is required")
        return self


@pydantic.dataclasses.dataclass
class ConfiguratorApplicationData:
    """Complete application databag payload published by one ``garm-configurator`` application.

    This is the write model for the relation: the configurator fills both nested values and
    publishes them with one ``ops.Relation.save``, so the application databag holds a
    ``provider`` object and a ``scaleset`` object instead of a flat set of keys.

    Attributes:
        provider: The provider and GitHub App credentials.
        scaleset: The scaleset and runner fields.
    """

    provider: ProviderConfig
    scaleset: ScalesetConfig


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
            The provider name the configurator wrote to the ``scaleset`` value, matching
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
        yields at most one entry. An empty or incomplete application databag is recorded as
        invalid, so a related application that has not published yet cannot be mistaken for one
        that left, and the consumer blocks on the partial aggregate instead of reconciling it.
        Relations that publish the same scaleset name are also rejected and marked invalid, so
        the consumer sees the conflict instead of a winner chosen by iteration order.

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
            try:
                application_data = relation.load(ConfiguratorApplicationData, application)
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
                provider=application_data.provider,
                scaleset=application_data.scaleset,
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
