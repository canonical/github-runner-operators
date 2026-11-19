# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the ``garm-configurator`` relation dataclasses."""

import dataclasses
from types import SimpleNamespace

import pydantic
import pytest
from garm_configurator_relation import (
    ConfiguratorApplicationData,
    ConfiguratorData,
    ConfiguratorRelation,
    GarmConfiguratorRequirer,
    ProviderConfig,
    ScalesetConfig,
)


def _provider(**overrides) -> ProviderConfig:
    """Return a complete provider payload, with the given fields overridden."""
    values = {
        "openstack_auth_url": "https://ks.example.com:5000/v3",
        "openstack_username": "admin",
        "openstack_password_secret_uri": "secret:openstack-password",
        "openstack_project_name": "myproject",
        "openstack_user_domain_name": "Default",
        "openstack_project_domain_name": "Default",
        "openstack_region_name": "RegionOne",
        "openstack_network": "external-net",
        "github_app_id": 123,
        "github_installation_id": 456,
        "github_private_key_secret_uri": "secret:github-private-key",
    }
    values.update(overrides)
    return ProviderConfig(**values)


def _scaleset(**overrides) -> ScalesetConfig:
    """Return a complete scaleset payload, with the given fields overridden."""
    values = {
        "name": "my-scaleset",
        "provider_name": "configurator-0",
        "image_id": "ubuntu:24.04",
        "flavor": "m1.large",
        "os_arch": "amd64",
        "repo": "myorg/myrepo",
    }
    values.update(overrides)
    return ScalesetConfig(**values)


def _relation(relation_id: int = 1, scaleset_name: str = "my-scaleset") -> ConfiguratorRelation:
    """Return a minimal valid configurator relation."""
    return ConfiguratorRelation(
        relation_id=relation_id,
        application_name=f"configurator-{relation_id}",
        provider=_provider(),
        scaleset=_scaleset(name=scaleset_name, provider_name=f"configurator-{relation_id}-0"),
    )


@pytest.mark.parametrize(
    "provider_name, expected",
    [
        pytest.param("configurator-0", "configurator-0", id="published-name"),
        pytest.param("", "", id="unset-name"),
    ],
)
def test_configurator_relation_provider_name(provider_name: str, expected: str):
    """
    arrange: A configurator relation whose scaleset value carries a provider name.
    act: Read its provider name.
    assert: The name published on the application databag is returned, matching GARM's provider
        registry and the provider name its scalesets reference.
    """
    relation = ConfiguratorRelation(
        relation_id=1,
        application_name="configurator",
        provider=ProviderConfig(openstack_auth_url="https://ks.example.com:5000/v3"),
        scaleset=ScalesetConfig(provider_name=provider_name),
    )

    assert relation.provider_name == expected


@pytest.mark.parametrize(
    "data, expected_empty, expected_invalid",
    [
        pytest.param(ConfiguratorData(), True, False, id="no-relations"),
        pytest.param(
            ConfiguratorData(relations=(_relation(),)),
            False,
            False,
            id="valid-relation",
        ),
        pytest.param(
            ConfiguratorData(invalid_relation_ids=frozenset({1})),
            False,
            True,
            id="only-invalid-relation",
        ),
    ],
)
def test_configurator_data_reports_empty_and_invalid_state(
    data: ConfiguratorData, expected_empty: bool, expected_invalid: bool
):
    """
    arrange: An aggregate with no, one valid, or only an invalid configurator relation.
    act: Read its emptiness and invalid-relation flag.
    assert: The flags distinguish an empty deployment from one that has valid data to
        reconcile and from one that must block on an incomplete relation.
    """
    assert data.is_empty is expected_empty
    assert data.has_invalid_relations is expected_invalid


def test_application_data_nests_provider_and_scaleset():
    """
    arrange: A complete configurator payload with provider credentials and scaleset fields.
    act: Serialise it the way ``ops.Relation.save`` does.
    assert: The databag has one ``provider`` object and one ``scaleset`` object, each holding
        only its own fields, so consumers parse the two concerns separately.
    """
    application_data = ConfiguratorApplicationData(
        provider=_provider(github_app_id=123),
        scaleset=_scaleset(
            name="my-scaleset",
            provider_name="configurator-0",
            image_id="ubuntu:24.04",
            max_runner="6",
        ),
    )

    nested = dataclasses.asdict(application_data)

    assert set(nested) == {"provider", "scaleset"}
    assert nested["provider"] == {
        "openstack_auth_url": "https://ks.example.com:5000/v3",
        "openstack_username": "admin",
        "openstack_password": None,
        "openstack_password_secret_uri": "secret:openstack-password",
        "openstack_project_name": "myproject",
        "openstack_user_domain_name": "Default",
        "openstack_project_domain_name": "Default",
        "openstack_region_name": "RegionOne",
        "openstack_network": "external-net",
        "github_app_id": 123,
        "github_installation_id": 456,
        "github_private_key_secret_uri": "secret:github-private-key",
    }
    assert nested["scaleset"]["name"] == "my-scaleset"
    assert nested["scaleset"]["provider_name"] == "configurator-0"
    assert nested["scaleset"]["max_runner"] == "6"
    assert "name" not in nested["provider"]
    assert "openstack_auth_url" not in nested["scaleset"]


class _FakeApp:
    """Minimal related application for exercising the requirer without a live model."""

    name = "configurator"


class _FakeRelation:
    """Relation whose application databag either holds a payload or is still empty."""

    id = 1

    def __init__(
        self,
        application_data: ConfiguratorApplicationData | None = None,
        *,
        validates: bool = True,
    ) -> None:
        self.app = _FakeApp()
        self.data = (
            {self.app: {"published": "true"}}
            if application_data is not None or not validates
            else {}
        )
        self._application_data = application_data
        self._validates = validates
        self.loaded_entity = None

    def load(self, cls, entity, *args, **kwargs):
        """Return the nested application payload, raising as ``ops`` does when it is absent."""
        if cls is not ConfiguratorApplicationData:
            raise AssertionError(f"unexpected databag load for {cls.__name__}")
        self.loaded_entity = entity
        if self._application_data is None or not self._validates:
            raise ValueError("incomplete application databag")
        return self._application_data


def test_requirer_reads_nested_provider_and_scaleset():
    """
    arrange: A configurator relation whose application databag holds nested provider and
        scaleset values.
    act: Aggregate the relation data.
    assert: The payload is read from the application databag and the relation exposes each
        nested value unchanged, so the configurator's single save remains the source of truth.
    """
    application_data = ConfiguratorApplicationData(
        provider=_provider(github_app_id=123),
        scaleset=_scaleset(
            name="my-scaleset",
            provider_name="configurator-0",
            org="myorg",
            repo="",
            max_runner="6",
        ),
    )
    relation = _FakeRelation(application_data)
    charm = SimpleNamespace(model=SimpleNamespace(relations={"garm-configurator": [relation]}))

    data = GarmConfiguratorRequirer(charm).get_data()

    assert relation.loaded_entity is relation.app
    assert len(data.relations) == 1
    assert data.relations[0].application_name == "configurator"
    assert data.relations[0].provider_name == "configurator-0"
    assert data.relations[0].provider.openstack_auth_url == "https://ks.example.com:5000/v3"
    assert data.relations[0].scaleset.name == "my-scaleset"
    assert data.relations[0].scaleset.org == "myorg"
    assert data.relations[0].scaleset.max_runner == "6"


def test_requirer_marks_relation_without_application_data_invalid():
    """
    arrange: A configurator relation whose leader has not published an application payload.
    act: Aggregate the relation data.
    assert: The relation is not exposed but is recorded as invalid, so GARM blocks on the
        partial aggregate instead of reconciling an unfinished relation.
    """
    relation = _FakeRelation()
    charm = SimpleNamespace(model=SimpleNamespace(relations={"garm-configurator": [relation]}))

    data = GarmConfiguratorRequirer(charm).get_data()

    assert not data.relations
    assert data.invalid_relation_ids == frozenset({relation.id})
    assert not data.is_empty
    assert data.has_invalid_relations


def test_scaleset_optional_fields_have_garm_defaults():
    """
    arrange: A scaleset payload with only the fields GARM cannot create the scaleset without.
    act: Read the optional fields.
    assert: They carry the GARM defaults, so a databag that omits them is valid instead of
        invalid or an empty scaleset.
    """
    scaleset = _scaleset()

    assert scaleset.min_idle_runner == "0"
    assert scaleset.max_runner == "1"
    assert scaleset.labels == ""
    assert scaleset.runner_group == "Default"
    assert scaleset.enable_shell == "false"
    assert scaleset.pre_install_scripts == ""
    assert scaleset.image_visibility == ""
    assert scaleset.security_group == ""


@pytest.mark.parametrize(
    "field",
    ["name", "provider_name", "image_id", "flavor", "os_arch"],
)
def test_scaleset_required_field_must_be_present_and_not_blank(field: str):
    """
    arrange: A scaleset payload missing one of the fields scaleset creation depends on, first
        omitted and then blank.
    act: Build the scaleset payload.
    assert: Both forms are rejected, so a consumer never creates a scaleset from a partial or
        empty required value.
    """
    missing = {
        key: value for key, value in dataclasses.asdict(_scaleset()).items() if key != field
    }
    with pytest.raises(pydantic.ValidationError):
        ScalesetConfig(**missing)
    with pytest.raises(pydantic.ValidationError):
        _scaleset(**{field: "   "})


@pytest.mark.parametrize(
    "entity",
    [{}, {"org": "myorg", "repo": "myorg/myrepo"}],
    ids=["neither-org-nor-repo", "both-org-and-repo"],
)
def test_scaleset_requires_exactly_one_entity(entity: dict):
    """
    arrange: A scaleset payload naming neither or both of the mutually exclusive entity fields.
    act: Build the scaleset payload.
    assert: It is rejected, because GARM registers runners to exactly one org or repo.
    """
    data = dataclasses.asdict(_scaleset()) | {"org": "", "repo": ""} | entity
    with pytest.raises(pydantic.ValidationError):
        ScalesetConfig(**data)


@pytest.mark.parametrize(
    "field",
    [
        "openstack_auth_url",
        "openstack_username",
        "openstack_project_name",
        "openstack_user_domain_name",
        "openstack_project_domain_name",
        "openstack_region_name",
        "openstack_network",
        "github_private_key_secret_uri",
    ],
)
def test_provider_required_field_must_be_present_and_not_blank(field: str):
    """
    arrange: A provider payload missing one of the fields provider or credential creation
        depends on, first omitted and then blank.
    act: Build the provider payload.
    assert: Both forms are rejected, so a consumer never renders a provider from a partial or
        empty required value.
    """
    missing = {
        key: value for key, value in dataclasses.asdict(_provider()).items() if key != field
    }
    with pytest.raises(pydantic.ValidationError):
        ProviderConfig(**missing)
    with pytest.raises(pydantic.ValidationError):
        _provider(**{field: "   "})


def test_provider_requires_a_password_source():
    """
    arrange: A provider payload with neither an inline password nor a password secret URI.
    act: Build the provider payload.
    assert: It is rejected, because GARM cannot authenticate to Keystone without one; either
        source is accepted on its own.
    """
    with pytest.raises(pydantic.ValidationError):
        _provider(openstack_password=None, openstack_password_secret_uri=None)

    assert _provider(
        openstack_password_secret_uri=None, openstack_password="pass"
    ).openstack_password
    assert _provider().openstack_password_secret_uri


def test_requirer_marks_incomplete_payload_invalid():
    """
    arrange: A configurator relation whose published payload cannot satisfy the required fields.
    act: Aggregate the relation data.
    assert: The relation id is reported invalid and no partial provider is exposed, so GARM
        blocks instead of rendering a partially configured provider.
    """
    relation = _FakeRelation(validates=False)
    charm = SimpleNamespace(model=SimpleNamespace(relations={"garm-configurator": [relation]}))

    data = GarmConfiguratorRequirer(charm).get_data()

    assert data.relations == ()
    assert data.invalid_relation_ids == frozenset({relation.id})
