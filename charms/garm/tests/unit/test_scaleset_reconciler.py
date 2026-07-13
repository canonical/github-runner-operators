# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

import base64

import pytest

from charm_state import RunnerConfig
from garm_client.models.template import Template
from runner_template import build_template_data
from scaleset_reconciler import ScalesetReconciler, ScalesetSpec, _effective_extra_specs


class _FakeProvider:
    def __init__(self, name):
        self.name = name


class _FakeTag:
    def __init__(self, name):
        self.name = name


class _FakeScaleset:
    def __init__(
        self,
        name,
        sid=1,
        image="ubuntu-22.04",
        flavor="m1.small",
        max_runners=5,
        min_idle_runners=0,
        github_runner_group=None,
        extra_specs=None,
        tags=None,
        template_id=None,
        enabled=True,
    ):
        self.name = name
        self.id = sid
        self.image = image
        self.flavor = flavor
        self.max_runners = max_runners
        self.min_idle_runners = min_idle_runners
        self.github_runner_group = github_runner_group
        self.extra_specs = extra_specs or {}
        self.tags = [_FakeTag(t) for t in (tags or [])]
        self.template_id = template_id
        self.enabled = enabled


class FakeGarmClient:
    """In-memory fake for GarmAuthenticatedClient.

    Records each create/update/delete as a tuple in the corresponding list so
    tests can assert on the resulting state rather than on mock call patterns.
    """

    def __init__(self, providers=None, scalesets=None, org_id="org-uuid", repo_id=None):
        self._providers = [_FakeProvider(n) for n in (providers or [])]
        self._scalesets = [
            _FakeScaleset(
                name=ss["name"],
                sid=ss.get("id", 1),
                image=ss.get("image", "ubuntu-22.04"),
                flavor=ss.get("flavor", "m1.small"),
                max_runners=ss.get("max_runners", 5),
                min_idle_runners=ss.get("min_idle_runners", 0),
                github_runner_group=ss.get("github_runner_group", None),
                extra_specs=ss.get("extra_specs", {}),
                tags=ss.get("tags", []),
                template_id=ss.get("template_id", None),
                enabled=ss.get("enabled", True),
            )
            for ss in (scalesets or [])
        ]
        self._org_id = org_id
        self._repo_id = repo_id
        self.created: list[tuple[str, str, object]] = []
        self.updated: list[tuple[int, object]] = []
        self.deleted: list[int] = []

    def list_providers(self):
        return self._providers

    def list_scalesets(self):
        return self._scalesets

    def find_org_id(self, _name):
        return self._org_id

    def find_repo_id(self, _name):
        return self._repo_id

    def create_org_scaleset(self, org_id, params):
        self.created.append(("org", org_id, params))

    def create_repo_scaleset(self, repo_id, params):
        self.created.append(("repo", repo_id, params))

    def update_scaleset(self, scaleset_id, params):
        self.updated.append((scaleset_id, params))

    def delete_scaleset(self, scaleset_id):
        self.deleted.append(scaleset_id)

    # Template stubs: return empty results so the reconciler's template path
    # is a no-op when no runner config is set.
    def list_templates(self, partial_name=None, os_type=None):
        return []

    def get_template(self, template_id):
        return None

    def create_template(self, name, data, description="", os_type="linux") -> object:
        return None

    def update_template(self, template_id, data):
        return None

    def delete_template(self, template_id):
        pass


def _spec(
    name="my-scaleset",
    provider_name="openstack-demo",
    image="ubuntu-22.04",
    flavor="m1.small",
    os_arch="amd64",
    min_idle=0,
    max_runners=5,
    entity_type="organization",
    entity_name="my-org",
    labels=None,
    runner_group="",
    pre_install_scripts=None,
    template_id=None,
    runner_config=None,
):
    return ScalesetSpec(
        name=name,
        provider_name=provider_name,
        image=image,
        flavor=flavor,
        os_arch=os_arch,
        min_idle_runners=min_idle,
        max_runners=max_runners,
        entity_type=entity_type,
        entity_name=entity_name,
        labels=labels or [],
        runner_group=runner_group,
        pre_install_scripts=pre_install_scripts or {},
        template_id=template_id,
        runner_config=runner_config or RunnerConfig(),
    )


def _reconcile(client, desired):
    ScalesetReconciler(client).reconcile(desired)


@pytest.mark.parametrize(
    "entity_type, entity_name, create_key, expected_entity_id",
    [
        ("organization", "my-org", "org", "org-uuid"),
        ("repository", "owner/repo", "repo", "repo-uuid"),
    ],
    ids=["org-entity", "repo-entity"],
)
def test_create_scaleset(entity_type, entity_name, create_key, expected_entity_id):
    """
    arrange: FakeGarmClient with the provider registered and no existing scalesets.
    act: Reconcile a desired spec for an org or repo entity.
    assert: Exactly one scaleset is created under the correct entity; no updates or deletes.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[],
        org_id="org-uuid" if entity_type == "organization" else None,
        repo_id="repo-uuid" if entity_type == "repository" else None,
    )
    _reconcile(client, [_spec(entity_type=entity_type, entity_name=entity_name)])

    assert len(client.created) == 1
    kind, entity_id, params = client.created[0]
    assert kind == create_key
    assert entity_id == expected_entity_id
    assert params.name == "my-scaleset"
    assert params.image == "ubuntu-22.04"
    assert params.flavor == "m1.small"
    assert params.enabled is True
    assert client.updated == []
    assert client.deleted == []


@pytest.mark.parametrize(
    "providers, org_id",
    [
        ([], "org-uuid"),
        (["openstack-demo"], None),
    ],
    ids=["provider-missing", "entity-not-registered"],
)
def test_create_deferred_when_dependency_missing(providers, org_id):
    """
    arrange: FakeGarmClient missing either the provider or the entity registration.
    act: Reconcile a desired spec.
    assert: No scaleset is created, updated, or deleted.
    """
    client = FakeGarmClient(providers=providers, scalesets=[], org_id=org_id)
    _reconcile(client, [_spec()])

    assert client.created == []
    assert client.updated == []
    assert client.deleted == []


def _existing_scaleset(**overrides):
    base = dict(
        name="my-scaleset",
        id=1,
        image="ubuntu-22.04",
        flavor="m1.small",
        max_runners=5,
        min_idle_runners=0,
        github_runner_group=None,
        extra_specs={},
        tags=[],
        enabled=True,
    )
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "changed_field, new_value, spec_kwarg",
    [
        ("image", "ubuntu-24.04", {"image": "ubuntu-24.04"}),
        ("flavor", "m1.large", {"flavor": "m1.large"}),
        ("max_runners", 10, {"max_runners": 10}),
        ("min_idle_runners", 2, {"min_idle": 2}),
        ("template_id", 7, {"template_id": 7}),
    ],
    ids=[
        "image-changed",
        "flavor-changed",
        "max-runners-changed",
        "min-idle-changed",
        "template-id-changed",
    ],
)
def test_update_when_field_changed(changed_field, new_value, spec_kwarg):
    """
    arrange: FakeGarmClient with one existing scaleset whose tracked field differs from spec.
    act: Reconcile a desired spec with the changed field.
    assert: Exactly one update is issued; no creates or deletes.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset()],
    )
    _reconcile(client, [_spec(**spec_kwarg)])

    assert len(client.updated) == 1
    scaleset_id, _ = client.updated[0]
    assert scaleset_id == 1
    assert client.created == []
    assert client.deleted == []


def test_no_update_when_scaleset_unchanged():
    """
    arrange: FakeGarmClient with one existing scaleset that matches the desired spec exactly.
    act: Reconcile with that spec.
    assert: No creates, updates, or deletes are issued.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset()],
    )
    _reconcile(client, [_spec()])

    assert client.created == []
    assert client.updated == []
    assert client.deleted == []


def test_update_when_scaleset_disabled():
    """
    arrange: FakeGarmClient with one existing disabled scaleset that otherwise matches.
    act: Reconcile the desired spec.
    assert: The reconciler enables the scaleset so GARM can spawn runners.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(enabled=False)],
    )
    _reconcile(client, [_spec()])

    assert len(client.updated) == 1
    _, params = client.updated[0]
    assert params.enabled is True


def test_delete_orphaned_scaleset():
    """
    arrange: FakeGarmClient with an observed scaleset not present in the desired set.
    act: Reconcile with a different desired scaleset name.
    assert: The orphaned scaleset id is in deleted; new scaleset is created.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(name="stale-scaleset", id=42)],
    )
    _reconcile(client, [_spec(name="new-scaleset")])

    assert client.deleted == [42]


def test_unnamed_observed_scaleset_is_skipped():
    """
    arrange: FakeGarmClient with one observed scaleset lacking a name.
    act: Reconcile an unrelated desired spec.
    assert: The unnamed observed scaleset is ignored rather than deleted under an empty-name key.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(name=None, id=42)],
    )
    _reconcile(client, [_spec(name="new-scaleset")])

    assert client.deleted == []


@pytest.mark.parametrize(
    "providers, scalesets, desired, expected_deleted",
    [
        ([], [], [], []),
        ([], [_existing_scaleset()], [_spec(name="my-scaleset")], []),
    ],
    ids=["empty-state", "deferred-spec-preserves-existing"],
)
def test_no_delete(providers, scalesets, desired, expected_deleted):
    """
    arrange: FakeGarmClient in an empty state or with a deferred (no-provider) spec.
    act: Reconcile.
    assert: No scalesets are deleted.
    """
    client = FakeGarmClient(providers=providers, scalesets=scalesets)
    _reconcile(client, desired)

    assert client.deleted == expected_deleted


def test_pre_install_scripts_passed_in_create():
    """
    arrange: FakeGarmClient with provider registered and no existing scalesets.
    act: Reconcile a spec containing pre_install_scripts.
    assert: Created scaleset params include extra_specs with the base64-encoded script
        mapping (GARM's extra_specs field is map[string][]byte on the wire).
    """
    scripts = {"setup.sh": "#!/bin/bash\napt-get update"}
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])
    _reconcile(client, [_spec(pre_install_scripts=scripts)])

    assert len(client.created) == 1
    _, _, params = client.created[0]
    assert params.extra_specs == {
        "pre_install_scripts": {
            name: base64.b64encode(content.encode()).decode() for name, content in scripts.items()
        }
    }


def test_aproxy_pre_install_script_injected_when_proxy_configured():
    """
    arrange: A spec with runner_config.runner_http_proxy set and one operator script.
    act: Reconcile a create.
    assert: The created params disable cloud-init package upgrades and carry both the
        operator script and a "00-aproxy" entry (sorts first) whose decoded content
        configures aproxy for the given proxy.
    """

    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])
    _reconcile(
        client,
        [
            _spec(
                pre_install_scripts={"pre_install.sh": "echo operator-script"},
                runner_config=RunnerConfig(runner_http_proxy="http://squid.internal:3128"),
            )
        ],
    )

    assert len(client.created) == 1
    _, _, params = client.created[0]
    assert params.extra_specs["disable_updates"] is True
    scripts = params.extra_specs["pre_install_scripts"]
    assert set(scripts.keys()) == {"00-aproxy", "pre_install.sh"}
    aproxy_script = base64.b64decode(scripts["00-aproxy"]).decode()
    assert "snap set aproxy proxy=squid.internal:3128" in aproxy_script


def test_no_update_when_extra_specs_already_match_encoded_desired_state():
    """
    arrange: An observed scaleset whose extra_specs already carry the base64-encoded
        aproxy + operator scripts and disable_updates, matching the desired spec.
    act: Reconcile that spec.
    assert: No update is issued.
    """

    proxy = "http://squid.internal:3128"
    spec = _spec(
        pre_install_scripts={"pre_install.sh": "echo operator-script"},
        runner_config=RunnerConfig(runner_http_proxy=proxy),
    )

    extra_specs = _effective_extra_specs(spec)
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(extra_specs=extra_specs)],
    )
    _reconcile(client, [spec])

    assert client.updated == []


def test_update_when_observed_scripts_are_legacy_raw_text():
    """
    arrange: An observed scaleset whose extra_specs carry raw-text (unencoded) script
        values from before base64-encoding was introduced.
    act: Reconcile a spec whose desired scripts are the same content.
    assert: An update is issued (the raw-text value never matches the encoded desired one).
    """

    spec = _spec(
        pre_install_scripts={"pre_install.sh": "echo operator-script"},
        runner_config=RunnerConfig(runner_http_proxy="http://squid.internal:3128"),
    )
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _existing_scaleset(
                extra_specs={
                    "disable_updates": True,
                    "pre_install_scripts": {"pre_install.sh": "echo operator-script"},
                }
            )
        ],
    )
    _reconcile(client, [spec])

    assert len(client.updated) == 1


def test_update_when_disable_updates_missing_but_proxy_configured():
    """
    arrange: An observed scaleset whose extra_specs carry the correctly-encoded scripts
        but lack disable_updates, while the spec configures a proxy.
    act: Reconcile that spec.
    assert: An update is issued to set disable_updates.
    """

    spec = _spec(runner_config=RunnerConfig(runner_http_proxy="http://squid.internal:3128"))
    extra_specs = _effective_extra_specs(spec)
    del extra_specs["disable_updates"]
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(extra_specs=extra_specs)],
    )
    _reconcile(client, [spec])

    assert len(client.updated) == 1


def test_update_clears_extra_specs_with_empty_dict_when_proxy_removed():
    """
    arrange: An observed scaleset carrying aproxy extra_specs, and a desired spec with no
        proxy (and no operator scripts) so the effective extra_specs are empty.
    act: Reconcile that spec.
    assert: The update sends an explicit empty dict — not None, which exclude_none would
        drop, leaving the stale extra_specs (and looping forever).
    """

    stale = _effective_extra_specs(
        _spec(runner_config=RunnerConfig(runner_http_proxy="http://squid.internal:3128"))
    )
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(extra_specs=stale)],
    )
    _reconcile(client, [_spec(runner_config=RunnerConfig())])

    assert len(client.updated) == 1
    _, params = client.updated[0]
    assert params.extra_specs == {}


class _FakeTemplate:
    """Minimal fake for the GARM Template model used in template lifecycle tests."""

    def __init__(self, name, tid, data=b"", description=""):
        self.name = name
        self.id = tid
        self.data = list(data) if isinstance(data, bytes) and data else data or None
        self.description = description


class _TemplateTrackingClient(FakeGarmClient):
    """FakeGarmClient variant that tracks template create/update/delete operations."""

    def __init__(self, templates=None, **kwargs):
        super().__init__(**kwargs)
        self._templates = list(templates or [])
        self.created_templates: list[tuple[str, bytes, str]] = []
        self.updated_templates: list[tuple[int, bytes]] = []
        self.deleted_templates: list[int] = []

    def list_templates(self, partial_name=None, os_type=None):
        if partial_name is None:
            return list(self._templates)
        return [t for t in self._templates if t.name and partial_name in t.name]

    def get_template(self, template_id):
        for t in self._templates:
            if t.id == template_id:
                return t
        return None

    def create_template(self, name, data, description="", os_type="linux") -> _FakeTemplate:  # type: ignore[override]
        tid = max((t.id for t in self._templates), default=0) + 1
        template = _FakeTemplate(name, tid, data, description)
        self._templates.append(template)
        self.created_templates.append((name, data, description))
        return template

    def update_template(self, template_id, data):
        for t in self._templates:
            if t.id == template_id:
                t.data = list(data)
                break
        self.updated_templates.append((template_id, data))

    def delete_template(self, template_id):
        self._templates = [t for t in self._templates if t.id != template_id]
        self.deleted_templates.append(template_id)


class _DeleteFailingTemplateClient(_TemplateTrackingClient):
    """TemplateTrackingClient variant whose delete_template raises a GARM API error."""

    def delete_template(self, template_id):
        from garm_api import GarmApiError

        raise GarmApiError(f"delete failed for template {template_id}")


_SYSTEM_TEMPLATE = _FakeTemplate("github_linux", tid=1, data=b"#!/bin/bash\nset -e\necho base\n")


def _spec_with_runner_config(**rc_kwargs):
    """Build a spec with runner_config populated from the given kwargs."""

    return _spec(runner_config=RunnerConfig(**rc_kwargs))


def test_template_created_when_runner_config_set():
    """
    arrange: No existing scalesets or custom templates; system template exists.
    act: Reconcile a spec with runner options (dockerhub_mirror).
    assert: A custom template is created and the scaleset references it via template_id.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[],
        templates=[_SYSTEM_TEMPLATE],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://mirror.example.com")],
    )

    assert len(client.created_templates) == 1
    name, data, _ = client.created_templates[0]
    assert name == "github_linux-my-scaleset"
    assert b"registry-mirrors" in data
    assert len(client.created) == 1
    _, _, params = client.created[0]
    # The created template's id is 2 (system=1, first custom=2)
    assert params.template_id == 2


def test_template_created_when_garm_returns_template_data_as_string():
    """
    arrange: The system template data is returned as a base64 string by the GARM API.
    act: Reconcile a spec with runner options.
    assert: A custom template is created from the decoded script data without hook errors.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[],
        templates=[
            _FakeTemplate(
                "github_linux",
                tid=1,
                data=base64.b64encode(b"#!/bin/bash\nset -e\necho base\n").decode(),
            )
        ],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://mirror.example.com")],
    )

    assert len(client.created_templates) == 1
    _, data, _ = client.created_templates[0]
    assert isinstance(data, bytes)
    assert b"registry-mirrors" in data
    assert b"#!/bin/bash" in data


def test_template_created_from_charmed_template_when_scaleset_references_it():
    """
    arrange: A scaleset references the charm-managed template and runner options are set.
    act: Reconcile the desired spec.
    assert: The custom template is derived from the charmed template rather than the bare system one.
    """

    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[],
        templates=[
            _SYSTEM_TEMPLATE,
            _FakeTemplate(
                "github_linux_charmed",
                tid=7,
                data=base64.b64encode(b"#!/bin/bash\nset -e\necho charmed-base\n").decode(),
            ),
        ],
    )
    _reconcile(
        client,
        [
            _spec(
                template_id=7,
                runner_config=RunnerConfig(dockerhub_mirror="https://mirror.example.com"),
            )
        ],
    )

    assert len(client.created_templates) == 1
    _, data, _ = client.created_templates[0]
    assert b"echo charmed-base" in data
    assert b"echo base" not in data


def test_template_updated_when_runner_config_changes():
    """
    arrange: A scaleset with an existing custom template.
    act: Reconcile with a changed runner config.
    assert: The custom template is updated (not recreated); the scaleset template_id is unchanged.
    """

    old_config = RunnerConfig(dockerhub_mirror="https://old.example.com")
    custom_template = _FakeTemplate(
        "github_linux-my-scaleset",
        tid=2,
        data=build_template_data(b"#!/bin/bash\nset -e\necho base\n", old_config),
    )
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(template_id=2)],
        templates=[_SYSTEM_TEMPLATE, custom_template],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://new.example.com")],
    )

    assert len(client.updated_templates) == 1
    template_id, data = client.updated_templates[0]
    assert template_id == 2
    assert b"new.example.com" in data
    assert b"old.example.com" not in data
    # Scaleset should not be updated just because template content changed.
    assert client.updated == []


def test_template_detached_when_runner_config_cleared():
    """
    arrange: A scaleset with an existing custom template.
    act: Reconcile with no runner options.
    assert: The scaleset is updated with template_id=0 (detach), and the custom template is deleted.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(template_id=2)],
        templates=[
            _SYSTEM_TEMPLATE,
            _FakeTemplate(
                "github_linux-my-scaleset", tid=2, data=b"#!/bin/bash\nset -e\necho x\n"
            ),
        ],
    )
    _reconcile(client, [_spec()])

    assert len(client.updated) == 1
    _, params = client.updated[0]
    assert params.template_id == 0
    assert 2 in client.deleted_templates


def test_template_kept_when_system_template_missing():
    """
    arrange: A scaleset with an existing custom template, but the system template is not listed.
    act: Reconcile with runner options still set.
    assert: The existing custom template is kept (not destroyed); no create/update/delete on templates.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(template_id=2)],
        templates=[
            _FakeTemplate(
                "github_linux-my-scaleset", tid=2, data=b"#!/bin/bash\nset -e\necho x\n"
            ),
        ],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://m.example.com")],
    )

    assert client.created_templates == []
    assert client.updated_templates == []
    assert client.deleted_templates == []


def test_template_with_missing_id_is_not_updated():
    """
    arrange: A custom template exists without an id and its rendered content differs.
    act: Reconcile a spec with runner options.
    assert: The reconciler skips the update and falls back to the default template id.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(template_id=2)],
        templates=[
            _SYSTEM_TEMPLATE,
            _FakeTemplate("github_linux-my-scaleset", tid=None, data=b"stale"),
        ],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://mirror.example.com")],
    )

    assert client.updated_templates == []
    assert len(client.updated) == 1
    _, params = client.updated[0]
    assert params.template_id == 0


def test_template_bytes_does_not_cache_invalid_placeholder_on_generated_model():
    """
    arrange: A generated Template model whose list response omits data and whose fetched body is still missing.
    act: Read template bytes through the reconciler helper.
    assert: Empty bytes are returned and the Template model is not assigned a non-string placeholder.
    """
    client = _TemplateTrackingClient()
    reconciler = ScalesetReconciler(client)
    listed = Template(id=5, name="github_linux")
    client._templates = [listed]

    assert reconciler._template_bytes(listed) == b""
    assert listed.data is None


def test_delete_custom_template_skips_missing_id_and_api_errors():
    """
    arrange: One custom template has no id and another raises on delete.
    act: Reconcile removal of the associated scalesets.
    assert: Missing-id templates are skipped and delete errors do not abort reconcile.
    """
    missing_id_client = _TemplateTrackingClient(
        templates=[_FakeTemplate("github_linux-stale", tid=None, data=b"x")],
    )
    _reconcile(missing_id_client, [])
    assert missing_id_client.deleted_templates == []

    failing_client = _DeleteFailingTemplateClient(
        templates=[_FakeTemplate("github_linux-stale", tid=7, data=b"x")],
    )
    _reconcile(failing_client, [])
