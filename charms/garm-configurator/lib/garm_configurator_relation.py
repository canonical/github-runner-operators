# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Models and requirer helpers for the ``garm-configurator`` relation data contract.

The ``garm-configurator`` charm owns the relation contract and publishes one provider
configuration per unit with ``ops.Relation.save``. ``ProviderConfig`` carries the provider and
GitHub App credentials (JSON-encoded, the default) and ``ScalesetConfig`` carries the scaleset
and runner fields (saved with ``encoder=str`` so their raw-string wire form is preserved). The
models live with the charm so consumers can share the same definitions and use
``ops.Relation.load`` instead of hand-writing databag keys.

The ``GarmConfiguratorRequirer`` aggregates every joined ``garm-configurator`` relation into a
single ``ConfiguratorData`` value. The ``garm`` charm uses that value to render provider
configurations and build its scalesets. A unit that has not published a complete provider
payload is invalid; its relation id is recorded in ``ConfiguratorData.invalid_relation_ids``
instead of being exposed as an empty provider. Relations that publish the same scaleset name
are also invalid: a scaleset name must identify exactly one scaleset in GARM.
"""

import dataclasses
import logging
import typing

import ops
import pydantic

logger = logging.getLogger(__name__)

GARM_CONFIGURATOR_RELATION_NAME: typing.Final[str] = "garm-configurator"


PROVIDER_TYPE_OPENSTACK: typing.Final[str] = "openstack"
PROVIDER_TYPE_LXD: typing.Final[str] = "lxd"
PROVIDER_TYPES: typing.Final = (PROVIDER_TYPE_OPENSTACK, PROVIDER_TYPE_LXD)

_OPENSTACK_REQUIRED_PROVIDER_FIELDS: typing.Final[tuple[str, ...]] = (
    "openstack_auth_url",
    "openstack_username",
    "openstack_project_name",
    "openstack_user_domain_name",
    "openstack_project_domain_name",
    "openstack_region_name",
    "openstack_network",
)
_OPENSTACK_PROVIDER_FIELDS: typing.Final[tuple[str, ...]] = (
    *_OPENSTACK_REQUIRED_PROVIDER_FIELDS,
    "openstack_password",
    "openstack_password_secret_uri",
)
_LXD_REQUIRED_PROVIDER_FIELDS: typing.Final[tuple[str, ...]] = (
    "lxd_api_url",
    "lxd_client_certificate_secret_uri",
    "lxd_client_key_secret_uri",
)
_LXD_PROVIDER_FIELDS: typing.Final[tuple[str, ...]] = (
    *_LXD_REQUIRED_PROVIDER_FIELDS,
    "lxd_project_name",
    "lxd_secure_boot",
    "lxd_server_certificate_secret_uri",
)


@pydantic.dataclasses.dataclass
class ProviderConfig:
    """Provider and GitHub App credentials published by one ``garm-configurator`` unit.

    The field names are the relation databag keys, so they are the wire contract between the
    configurator and GARM. ``provider_type`` selects which fields a unit publishes: the
    selected provider's required fields must be present and the other provider's fields must
    stay unset, so a payload cannot mix OpenStack and LXD settings.

    Attributes:
        provider_type: Provider type, "openstack" or "lxd".
        openstack_auth_url: Keystone authentication URL.
        openstack_username: OpenStack username.
        openstack_password: Legacy plaintext password, or None when the secret URI is used.
        openstack_password_secret_uri: Juju secret URI holding the password.
        openstack_project_name: OpenStack project (tenant).
        openstack_user_domain_name: Domain of the user.
        openstack_project_domain_name: Domain of the project.
        openstack_region_name: OpenStack region.
        openstack_network: Network name or ID instances are attached to.
        lxd_api_url: LXD API URL.
        lxd_project_name: LXD project instances are created in.
        lxd_secure_boot: Whether LXD virtual machines use secure boot.
        lxd_client_certificate_secret_uri: Juju secret URI holding the client certificate.
        lxd_client_key_secret_uri: Juju secret URI holding the client key.
        lxd_server_certificate_secret_uri: Juju secret URI holding the server certificate.
        github_app_id: GitHub App ID.
        github_installation_id: GitHub App installation ID.
        github_private_key_secret_uri: Juju secret URI holding the GitHub App private key.
    """

    provider_type: str
    openstack_auth_url: str | None = None
    openstack_username: str | None = None
    openstack_password: str | None = None
    openstack_password_secret_uri: str | None = None
    openstack_project_name: str | None = None
    openstack_user_domain_name: str | None = None
    openstack_project_domain_name: str | None = None
    openstack_region_name: str | None = None
    openstack_network: str | None = None
    lxd_api_url: str | None = None
    lxd_project_name: str | None = None
    lxd_secure_boot: bool = False
    lxd_client_certificate_secret_uri: str | None = None
    lxd_client_key_secret_uri: str | None = None
    lxd_server_certificate_secret_uri: str | None = None
    github_app_id: int | None = None
    github_installation_id: int | None = None
    github_private_key_secret_uri: str | None = None

    @pydantic.field_validator("provider_type", mode="before")
    @classmethod
    def _normalize_provider_type(cls, value: object) -> str:
        """Normalize and validate the provider type."""
        normalized = str(value or "").strip().lower()
        if normalized not in PROVIDER_TYPES:
            raise ValueError(f"provider_type must be one of: {', '.join(PROVIDER_TYPES)}")
        return normalized

    @pydantic.model_validator(mode="after")
    def _validate_provider_fields(self) -> "ProviderConfig":
        """Require the selected provider's fields and reject the other provider's fields."""
        if self.provider_type == PROVIDER_TYPE_LXD:
            required_fields = _LXD_REQUIRED_PROVIDER_FIELDS
            forbidden_fields = _OPENSTACK_PROVIDER_FIELDS
        else:
            required_fields = _OPENSTACK_REQUIRED_PROVIDER_FIELDS
            forbidden_fields = _LXD_PROVIDER_FIELDS

        missing = [name for name in required_fields if not getattr(self, name)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        conflicting = [
            name for name in forbidden_fields if _provider_field_is_set(name, getattr(self, name))
        ]
        if conflicting:
            raise ValueError(
                f"Fields not allowed for provider_type {self.provider_type}: "
                f"{', '.join(conflicting)}"
            )
        return self


def _provider_field_is_set(field_name: str, value: object) -> bool:
    """Return whether a provider field holds a non-default value.

    Args:
        field_name: The provider model field name.
        value: The field value.

    Returns:
        True when the field was set away from its default.
    """
    if field_name == "lxd_project_name":
        return value not in ("", None, "default")
    return bool(value)


@dataclasses.dataclass(frozen=True)
class ScalesetConfig:
    """Scaleset and runner fields published by one ``garm-configurator`` unit.

    The configurator fills this model and saves it with ``encoder=str``, which keeps the
    relation's raw-string wire form so older consumers can still read it. The fields are also
    loaded directly with ``decoder=str`` on the consuming side. An empty string means "unset".

    These fields are still published on the unit databag. The configurator runs no workload and
    always deploys a single unit, so they belong on the application databag instead; that move is
    deliberately left to a follow-up so this change can stay incremental.

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


# A scaleset name identifies the scaleset; a provider can legitimately serve several scalesets,
# so provider_name is not part of the identity.
_SCALESET_UNIQUE_FIELDS: typing.Final = ("name",)


@dataclasses.dataclass(frozen=True)
class ConfiguratorData:
    """Every ``garm-configurator`` relation unit, aggregated for one reconcile pass.

    The requirer builds this value: it only exposes relations it could load and marks every
    relation it rejected in ``invalid_relation_ids``.

    Attributes:
        relations: One valid entry per related unit.
        invalid_relation_ids: Relation ids whose unit databag is incomplete, malformed, or
            conflicts with another relation over a scaleset identity field.
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

        A unit whose provider payload cannot be loaded is skipped and its relation id is recorded
        as invalid, so the consumer never renders a half-written provider. Relations that publish
        the same scaleset name are also rejected and marked invalid, so the consumer sees the
        conflict instead of a winner chosen by iteration order.

        Returns:
            The valid relation data for every related unit, plus the ids of invalid relations.
        """
        aggregated: list[ConfiguratorRelation] = []
        invalid_relation_ids: set[int] = set()
        relations_by_identity: dict[tuple[str, ...], list[ConfiguratorRelation]] = {}
        relations = self._charm.model.relations.get(self._relation_name, [])
        for relation in relations:
            application_name = relation.app.name if relation.app else ""
            for unit in relation.units:
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
                configurator_relation = ConfiguratorRelation(
                    relation_id=relation.id,
                    application_name=application_name,
                    unit_name=unit.name,
                    provider=provider,
                    scaleset=relation.load(ScalesetConfig, unit, decoder=str),
                )
                aggregated.append(configurator_relation)
                identity = tuple(
                    getattr(configurator_relation.scaleset, field)
                    for field in _SCALESET_UNIQUE_FIELDS
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
