# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

import base64
import datetime
import logging

import pytest

from charm_state import RunnerConfig
from garm_api import GarmApiError, GarmConnectionError
from garm_client.models.template import Template
from runner_template import build_template_data
from scaleset_reconciler import (
    DRAIN_DEADLINE,
    MAX_SCALESET_NAME_LENGTH,
    Handover,
    ScalesetProgress,
    ScalesetReconciler,
    ScalesetSpec,
    _effective_extra_specs,
    target_scaleset_name,
)


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
        updated_at=None,
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
        # GARM tags Enabled `omitempty` and has no custom marshaller, so a disabled
        # scaleset arrives with no `enabled` key at all and the generated client reads
        # it back as None — `False` is a shape the API never returns. Model the wire,
        # or the whole retirement half of this suite passes against a fiction.
        self.enabled = True if enabled else None
        # GARM stamps this on every write, so for a retired scaleset it is the
        # moment it was disabled — which is what the drain deadline measures from.
        self.updated_at = updated_at or datetime.datetime.now(datetime.timezone.utc)


class FakeGarmClient:
    """In-memory fake for GarmAuthenticatedClient.

    Records each create/update/delete as a tuple in the corresponding list so
    tests can assert on the resulting state rather than on mock call patterns.
    """

    def __init__(
        self,
        providers=None,
        scalesets=None,
        org_id="org-uuid",
        repo_id=None,
        instances=None,
        reject_zero_max_runners=False,
    ):
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
                updated_at=ss.get("updated_at", None),
            )
            for ss in (scalesets or [])
        ]
        self._org_id = org_id
        self._repo_id = repo_id
        # Runner counts per scaleset id, so a draining scaleset can be modelled.
        self._instances = instances or {}
        self.reject_zero_max_runners = reject_zero_max_runners
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

    def list_scaleset_instances(self, scaleset_id):
        return [object()] * self._instances.get(scaleset_id, 0)

    def update_scaleset(self, scaleset_id, params):
        # Models a GARM that rejects max_runners=0 on update. Today's GARM does not
        # (see _retire), so this only exercises the reconciler's defensive fallback.
        if self.reject_zero_max_runners and params.max_runners == 0:
            raise GarmApiError("max_runners must be greater than 0")
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
    return ScalesetReconciler(client).reconcile(desired)


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
    assert params.name == target_scaleset_name("my-scaleset", [])
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


def test_orphan_template_outlives_a_failed_orphan_delete():
    """
    arrange: An orphaned scaleset with a custom template, whose deletion GARM rejects.
    act: Reconcile a different desired scaleset.
    assert: Its template is kept — the scaleset still exists and its runners were built
        from that template, and the next reconcile's retry still needs it.
    """

    class _DeleteFailingClient(_TemplateTrackingClient):
        def delete_scaleset(self, scaleset_id):
            raise GarmApiError("scaleset still has runners")

    client = _DeleteFailingClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(name="stale-scaleset", id=42, template_id=2)],
        templates=[
            _SYSTEM_TEMPLATE,
            _FakeTemplate("github_linux-stale-scaleset", tid=2, data=b"x"),
        ],
    )

    _reconcile(client, [_spec(name="new-scaleset")])

    assert client.deleted == []
    assert client.deleted_templates == []


def test_a_connection_error_during_the_orphan_sweep_is_not_reported_as_converged():
    """
    arrange: An orphaned scaleset and a GARM that has become unreachable.
    act: Reconcile a different desired scaleset.
    assert: The error propagates rather than being contained per-scaleset, so the charm
        reports the outage instead of an orphan sweep that appears to have finished.
    """

    class _UnreachableClient(FakeGarmClient):
        def update_scaleset(self, scaleset_id, params):
            raise GarmConnectionError("connection refused")

    client = _UnreachableClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(name="stale-scaleset", id=42)],
    )

    with pytest.raises(GarmConnectionError):
        _reconcile(client, [_spec(name="new-scaleset")])


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
    assert name == f"github_linux-{target_scaleset_name('my-scaleset', [])}"
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


# A label change is applied by replacement (docs/adr/003); "generation" below means
# one live scaleset of a logical spec.
_LABELS_OLD = ["jammy", "x64"]
_LABELS_NEW = ["jammy", "arm64"]
_OLD_NAME = target_scaleset_name("my-scaleset", _LABELS_OLD)
_NEW_NAME = target_scaleset_name("my-scaleset", _LABELS_NEW)


def _generation(labels, **overrides):
    """An existing scaleset named and tagged as the reconciler would have created it."""
    base = _existing_scaleset(
        name=target_scaleset_name("my-scaleset", labels), tags=sorted(labels)
    )
    base.update(overrides)
    return base


def test_create_uses_label_hashed_name():
    """
    arrange: FakeGarmClient with the provider registered and no existing scalesets.
    act: Reconcile a spec carrying labels.
    assert: The scaleset is created under the label-hashed name, so a later label change
        resolves to a different name and can be applied by replacement.
    """
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])

    _reconcile(client, [_spec(labels=_LABELS_OLD)])

    assert len(client.created) == 1
    _, _, params = client.created[0]
    assert params.name == _OLD_NAME
    assert params.labels == sorted(_LABELS_OLD)


def test_legacy_unsuffixed_scaleset_adopted_when_labels_match():
    """
    arrange: A scaleset carrying the pre-hash un-suffixed name, with the desired labels.
    act: Reconcile the matching spec.
    assert: It is adopted in place — upgrading the charm must not churn scalesets that
        are already serving the right labels.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset(name="my-scaleset", tags=sorted(_LABELS_OLD))],
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_OLD)])

    assert client.created == []
    assert client.deleted == []
    assert progress == []


def test_label_change_creates_replacement_without_disabling_the_old_one():
    """
    arrange: One live scaleset serving the old labels.
    act: Reconcile a spec whose labels changed.
    assert: The replacement is created and the old scaleset is left enabled, so jobs keep
        being served until the replacement actually exists.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1)],
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert len(client.created) == 1
    _, _, params = client.created[0]
    assert params.name == _NEW_NAME
    assert client.updated == []
    assert client.deleted == []
    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 0, Handover.PENDING)]


def test_cutover_disables_and_zeroes_the_old_scaleset():
    """
    arrange: Both generations live, the replacement already enabled.
    act: Reconcile.
    assert: Only the old scaleset is disabled and zeroed — disabling closes its listener
        session, which is what hands the shared labels to the replacement.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1), _generation(_LABELS_NEW, id=2)],
        instances={1: 3},
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.created == []
    assert client.deleted == []
    assert len(client.updated) == 1
    scaleset_id, params = client.updated[0]
    assert scaleset_id == 1
    assert params.enabled is False
    assert params.min_idle_runners == 0
    assert params.max_runners == 0
    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 3)]


def test_cutover_falls_back_when_zeroing_max_runners_is_rejected():
    """
    arrange: Both generations live and a hypothetical GARM refuses max_runners=0 on
        update, which today's GARM accepts.
    act: Reconcile.
    assert: The scaleset is still disabled, so the handover happens even though the
        runner counts could not be zeroed.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1), _generation(_LABELS_NEW, id=2)],
        reject_zero_max_runners=True,
    )

    _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert len(client.updated) == 1
    scaleset_id, params = client.updated[0]
    assert scaleset_id == 1
    assert params.enabled is False
    assert params.max_runners is None


def test_a_refused_cutover_is_not_reported_as_a_drain():
    """
    arrange: Both generations live, and GARM refuses to disable the old one.
    act: Reconcile.
    assert: The stalled hand-over is reported instead of a runner count: the predecessor
        is still enabled, so nothing is draining and a plausible "draining N runners"
        would hide a changeover that is not advancing (and is running both generations'
        idle runners meanwhile).
    """

    class _DisableFailsClient(FakeGarmClient):
        def update_scaleset(self, scaleset_id, params):
            raise GarmApiError("scaleset is locked")

    client = _DisableFailsClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1), _generation(_LABELS_NEW, id=2)],
        instances={1: 3},
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 0, Handover.FAILED)]


def test_draining_scaleset_is_not_deleted_while_runners_remain():
    """
    arrange: The old generation is already disabled and still has runners.
    act: Reconcile.
    assert: It is not deleted, so jobs already running on it can finish; the remaining
        count is reported so the charm can show progress.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False),
            _generation(_LABELS_NEW, id=2),
        ],
        instances={1: 2},
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == []
    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 2)]


def test_drained_scaleset_is_deleted_with_its_template():
    """
    arrange: The old generation is disabled with no runners left, and owns a template.
    act: Reconcile.
    assert: Both the scaleset and its template are deleted and nothing is left draining,
        so no idle scaleset lingers on GitHub.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False, template_id=2),
            _generation(_LABELS_NEW, id=2),
        ],
        templates=[_SYSTEM_TEMPLATE, _FakeTemplate(f"github_linux-{_OLD_NAME}", tid=2, data=b"x")],
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == [1]
    assert client.deleted_templates == [2]
    assert progress == []


def test_retiring_generation_is_not_treated_as_an_orphan():
    """
    arrange: Both generations live while the spec still exists.
    act: Reconcile.
    assert: The old generation is disabled rather than deleted outright — the orphan pass
        must not shortcut the drain and kill runners mid-job.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1), _generation(_LABELS_NEW, id=2)],
        instances={1: 1},
    )

    _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == []


def test_every_generation_is_deleted_when_the_spec_is_removed():
    """
    arrange: Two generations live and no desired specs at all.
    act: Reconcile.
    assert: Both are disabled and deleted — removing the relation must not leave a
        generation behind.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1), _generation(_LABELS_NEW, id=2)],
    )

    _reconcile(client, [])

    assert sorted(client.deleted) == [1, 2]


def test_label_revert_re_adopts_the_draining_scaleset():
    """
    arrange: The old generation is disabled and draining, the new one is live.
    act: Reconcile a spec whose labels are reverted to the old ones.
    assert: The disabled scaleset is re-enabled and no third scaleset is created — its
        name is again the target name, so it is simply adopted back.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False),
            _generation(_LABELS_NEW, id=2),
        ],
    )

    _reconcile(client, [_spec(labels=_LABELS_OLD)])

    assert client.created == []
    scaleset_id, params = client.updated[0]
    assert scaleset_id == 1
    assert params.enabled is True


def test_two_label_changes_retire_both_older_generations():
    """
    arrange: Three generations live: two superseded ones and the current one.
    act: Reconcile the spec for the newest labels.
    assert: Both older generations are disabled independently — a second label change
        mid-drain must not strand the first one.
    """
    labels_newest = ["jammy", "s390x"]
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1),
            _generation(_LABELS_NEW, id=2),
            _generation(labels_newest, id=3),
        ],
        instances={1: 1, 2: 1},
    )

    progress = _reconcile(client, [_spec(labels=labels_newest)])

    assert sorted(scaleset_id for scaleset_id, _ in client.updated) == [1, 2]
    assert all(params.enabled is False for _, params in client.updated)
    assert len(progress) == 2


def test_a_similarly_named_scaleset_is_not_claimed_as_a_generation():
    """
    arrange: Two specs whose names differ only by something that looks like a hash suffix.
    act: Reconcile both.
    assert: Neither scaleset is disabled or deleted, so one spec cannot retire the other's
        scaleset just because the names overlap.
    """
    sibling = "my-scaleset-1a2b3c4d"
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _existing_scaleset(name=target_scaleset_name("my-scaleset", []), id=1),
            _existing_scaleset(name=target_scaleset_name(sibling, []), id=2),
        ],
    )

    progress = _reconcile(client, [_spec(), _spec(name=sibling)])

    assert client.created == []
    assert client.deleted == []
    assert progress == []


def test_unexpected_labels_do_not_freeze_the_other_fields():
    """
    arrange: The target-named scaleset exists but carries labels that don't match the spec
        (GARM normalised the tags, a hash collision, or a hand-edited scaleset), and its
        image is stale.
    act: Reconcile a spec that needs an image update.
    assert: The image is still updated — labels cannot be fixed by an update, so refusing
        to update would freeze every unrelated field for as long as the mismatch lasts.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _existing_scaleset(
                name=target_scaleset_name("my-scaleset", _LABELS_NEW),
                tags=["something", "else"],
                image="ubuntu-20.04",
            )
        ],
    )

    _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert len(client.updated) == 1
    assert client.updated[0][1].image == "ubuntu-22.04"


def test_long_names_sharing_a_prefix_get_distinct_scalesets():
    """
    arrange: Two specs whose names are too long for a scaleset name and share a prefix,
        with identical labels.
    act: Reconcile both.
    assert: Two scalesets are created under distinct names — truncating to a shared prefix
        would collapse them onto one scaleset that both specs then fight over.
    """
    prefix = "a" * MAX_SCALESET_NAME_LENGTH
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])

    _reconcile(client, [_spec(name=f"{prefix}-one"), _spec(name=f"{prefix}-two")])

    created_names = [params.name for _, _, params in client.created]
    assert len(set(created_names)) == 2
    assert all(len(name) <= MAX_SCALESET_NAME_LENGTH for name in created_names)


def test_drained_scaleset_survives_an_unreadable_runner_count():
    """
    arrange: The old generation is disabled and its instance listing fails.
    act: Reconcile.
    assert: It is not deleted — an unknown runner count must never be mistaken for a
        drained scaleset and take live runners down with it.
    """

    class _InstanceListingFailsClient(FakeGarmClient):
        def list_scaleset_instances(self, scaleset_id):
            raise GarmApiError("boom")

    client = _InstanceListingFailsClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False),
            _generation(_LABELS_NEW, id=2),
        ],
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == []
    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 1)]


def test_template_outlives_a_failed_scaleset_delete():
    """
    arrange: The old generation is drained but GARM rejects its deletion.
    act: Reconcile.
    assert: Its template is kept — deleting the template of a scaleset that still exists
        would strip the runner config the next delete attempt still relies on.
    """

    class _DeleteFailingClient(_TemplateTrackingClient):
        def delete_scaleset(self, scaleset_id):
            raise GarmApiError("scaleset still has runners")

    client = _DeleteFailingClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False, template_id=2),
            _generation(_LABELS_NEW, id=2),
        ],
        templates=[_SYSTEM_TEMPLATE, _FakeTemplate(f"github_linux-{_OLD_NAME}", tid=2, data=b"x")],
    )

    _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == []
    assert client.deleted_templates == []


def test_failed_delete_keeps_the_replacement_reported_as_unfinished():
    """
    arrange: The old generation is drained but GARM rejects its deletion.
    act: Reconcile.
    assert: It is still reported as in flight — a scaleset GARM refused to delete is
        still on GitHub, so reporting the charm as converged would hide it.
    """

    class _DeleteFailingClient(FakeGarmClient):
        def delete_scaleset(self, scaleset_id):
            raise GarmApiError("scaleset still has runners")

    client = _DeleteFailingClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False),
            _generation(_LABELS_NEW, id=2),
        ],
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 0)]


def test_drain_past_the_deadline_stops_waiting_on_the_runner_count():
    """
    arrange: The old generation was disabled longer ago than any job can run, and still
        reports a runner (one stuck in a provider-side failure GARM never reaped).
    act: Reconcile.
    assert: The delete is attempted anyway, so a permanently faulted instance cannot pin
        a dead scaleset on GitHub forever; GARM itself rejects the call while runners are
        genuinely active, so no in-flight job is cut short.
    """
    long_ago = datetime.datetime.now(datetime.timezone.utc) - DRAIN_DEADLINE * 2
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False, updated_at=long_ago),
            _generation(_LABELS_NEW, id=2),
        ],
        instances={1: 1},
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == [1]
    assert progress == []


def test_drain_within_the_deadline_still_waits_for_the_runners():
    """
    arrange: The old generation was disabled recently and still has a runner.
    act: Reconcile.
    assert: It is not deleted — the deadline is a backstop for stuck instances, and must
        not shorten a normal drain and cut a running job short.
    """
    recently = datetime.datetime.now(datetime.timezone.utc) - DRAIN_DEADLINE / 2
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False, updated_at=recently),
            _generation(_LABELS_NEW, id=2),
        ],
        instances={1: 1},
    )

    progress = _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == []
    assert progress == [ScalesetProgress("my-scaleset", _OLD_NAME, _NEW_NAME, 1)]


@pytest.mark.parametrize(
    "updated_at",
    [
        None,
        # Naive, and far enough back that no timezone offset can bring it inside the
        # deadline — the point is that it is read as a timestamp at all, not crashed on.
        datetime.datetime.now() - datetime.timedelta(days=30),
    ],
    ids=["no-timestamp", "naive-timestamp"],
)
def test_drain_deadline_handles_an_unusable_timestamp(updated_at):
    """
    arrange: The old generation is draining and GARM reports no update timestamp, or a
        naive one (no timezone).
    act: Reconcile.
    assert: Neither crashes: a missing timestamp keeps waiting rather than reading as an
        expired deadline, and a naive one is read as UTC.
    """
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=False),
            _generation(_LABELS_NEW, id=2),
        ],
        instances={1: 1},
    )
    client._scalesets[0].updated_at = updated_at

    _reconcile(client, [_spec(labels=_LABELS_NEW)])

    assert client.deleted == ([] if updated_at is None else [1])


def test_a_failing_spec_does_not_wedge_the_others():
    """
    arrange: Two specs, the first of which GARM refuses to create.
    act: Reconcile.
    assert: The second is still created and the failure is re-raised, so one bad spec
        cannot freeze every other scaleset while the charm still reports the sync failed.
    """

    class _FirstCreateFailsClient(FakeGarmClient):
        def create_org_scaleset(self, org_id, params):
            if params.name.startswith("bad-"):
                raise GarmApiError("labels rejected")
            super().create_org_scaleset(org_id, params)

    client = _FirstCreateFailsClient(providers=["openstack-demo"], scalesets=[])

    with pytest.raises(GarmApiError):
        _reconcile(client, [_spec(name="bad-scaleset"), _spec(name="good-scaleset")])

    assert [params.name for _, _, params in client.created] == [
        target_scaleset_name("good-scaleset", [])
    ]


def test_a_failing_spec_does_not_hand_its_scalesets_to_the_orphan_pass():
    """
    arrange: A spec whose update GARM rejects, with its scaleset already live.
    act: Reconcile.
    assert: The scaleset is not deleted — a transient API failure must never be read as
        "this scaleset is no longer wanted".
    """

    class _UpdateFailsClient(FakeGarmClient):
        def update_scaleset(self, scaleset_id, params):
            raise GarmApiError("boom")

    client = _UpdateFailsClient(
        providers=["openstack-demo"],
        scalesets=[_generation(_LABELS_OLD, id=1, image="ubuntu-20.04")],
    )

    with pytest.raises(GarmApiError):
        _reconcile(client, [_spec(labels=_LABELS_OLD)])

    assert client.deleted == []


def test_a_connection_error_aborts_the_pass_immediately():
    """
    arrange: Two specs and a GARM that is unreachable.
    act: Reconcile.
    assert: The error propagates without attempting the second spec — GARM is down, so
        retrying every remaining spec would only stall the hook.
    """

    class _UnreachableClient(FakeGarmClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.attempts = 0

        def create_org_scaleset(self, org_id, params):
            self.attempts += 1
            raise GarmConnectionError("connection refused")

    client = _UnreachableClient(providers=["openstack-demo"], scalesets=[])

    with pytest.raises(GarmConnectionError):
        _reconcile(client, [_spec(name="one"), _spec(name="two")])

    assert client.attempts == 1


class _UnreachableWhenRetiring(FakeGarmClient):
    def update_scaleset(self, scaleset_id, params):
        raise GarmConnectionError("connection refused")


class _UnreachableWhenCounting(FakeGarmClient):
    def list_scaleset_instances(self, scaleset_id):
        raise GarmConnectionError("connection refused")


class _UnreachableWhenDeleting(FakeGarmClient):
    def delete_scaleset(self, scaleset_id):
        raise GarmConnectionError("connection refused")


@pytest.mark.parametrize(
    "client_class, old_enabled",
    [
        (_UnreachableWhenRetiring, True),
        (_UnreachableWhenCounting, False),
        (_UnreachableWhenDeleting, False),
    ],
    ids=["retiring", "counting-runners", "deleting"],
)
def test_a_connection_error_during_a_drain_is_not_reported_as_progress(client_class, old_enabled):
    """
    arrange: A generation being retired or already draining, and a GARM that is unreachable
        at each of the three calls the drain makes.
    act: Reconcile.
    assert: The error propagates rather than being contained as a per-scaleset failure, so
        the charm reports the outage instead of a drain that is not actually advancing.
        GarmConnectionError subclasses GarmApiError, so the containing handlers would
        otherwise swallow it and report progress.
    """
    client = client_class(
        providers=["openstack-demo"],
        scalesets=[
            _generation(_LABELS_OLD, id=1, enabled=old_enabled),
            _generation(_LABELS_NEW, id=2),
        ],
    )

    with pytest.raises(GarmConnectionError):
        _reconcile(client, [_spec(labels=_LABELS_NEW)])


def test_duplicate_desired_names_are_ignored(caplog):
    """
    arrange: Two specs sharing a logical name but carrying different labels.
    act: Reconcile.
    assert: Only the first is applied, and the conflict is warned about — both would own
        the other's scaleset and retire it on every reconcile, replacing each other forever.
    """
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])

    with caplog.at_level(logging.WARNING):
        progress = _reconcile(
            client,
            [_spec(labels=_LABELS_OLD), _spec(labels=_LABELS_NEW)],
        )

    assert [params.name for _, _, params in client.created] == [_OLD_NAME]
    assert progress == []
    assert "duplicate desired scaleset my-scaleset" in caplog.text


def test_identical_duplicate_specs_are_not_warned_about(caplog):
    """
    arrange: Two identical specs, as a multi-unit garm-configurator produces — the scaleset
        config is app-level, so every unit's databag yields the same spec.
    act: Reconcile.
    assert: One scaleset is created and nothing is warned about: the duplicate is the
        expected shape of a scaled configurator, not an operator misconfiguration, and
        warning on it would fire on every hook.
    """
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])

    with caplog.at_level(logging.WARNING):
        _reconcile(client, [_spec(labels=_LABELS_OLD), _spec(labels=_LABELS_OLD)])

    assert [params.name for _, _, params in client.created] == [_OLD_NAME]
    assert "duplicate" not in caplog.text
