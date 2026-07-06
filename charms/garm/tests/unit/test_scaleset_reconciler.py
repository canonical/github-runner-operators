# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

import pytest

from scaleset_reconciler import ScalesetReconciler, ScalesetSpec


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
    from runner_template import RunnerConfig

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
    assert: Created scaleset params include extra_specs with the script mapping.
    """
    scripts = {"setup.sh": "#!/bin/bash\napt-get update"}
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])
    _reconcile(client, [_spec(pre_install_scripts=scripts)])

    assert len(client.created) == 1
    _, _, params = client.created[0]
    assert params.extra_specs == {"pre_install_scripts": scripts}


# ---------------------------------------------------------------------------
# Runner template lifecycle tests
# ---------------------------------------------------------------------------


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


_SYSTEM_TEMPLATE = _FakeTemplate("github_linux", tid=1, data=b"#!/bin/bash\nset -e\necho base\n")


def _spec_with_runner_config(**rc_kwargs):
    """Build a spec with runner_config populated from the given kwargs."""
    from runner_template import RunnerConfig

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
    arrange: The system template data is returned as a string by the GARM API.
    act: Reconcile a spec with runner options.
    assert: A custom template is created from the string data without hook errors.
    """
    client = _TemplateTrackingClient(
        providers=["openstack-demo"],
        scalesets=[],
        templates=[_FakeTemplate("github_linux", tid=1, data="#!/bin/bash\nset -e\necho base\n")],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://mirror.example.com")],
    )

    assert len(client.created_templates) == 1
    _, data, _ = client.created_templates[0]
    assert isinstance(data, bytes)
    assert b"registry-mirrors" in data


def test_template_updated_when_runner_config_changes():
    """
    arrange: A scaleset with an existing custom template.
    act: Reconcile with a changed runner config.
    assert: The custom template is updated (not recreated); the scaleset template_id is unchanged.
    """
    from runner_template import build_template_data
    from runner_template import RunnerConfig

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
            _FakeTemplate("github_linux-my-scaleset", tid=2, data=b"#!/bin/bash\nset -e\necho x\n"),
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
            _FakeTemplate("github_linux-my-scaleset", tid=2, data=b"#!/bin/bash\nset -e\necho x\n"),
        ],
    )
    _reconcile(
        client,
        [_spec_with_runner_config(dockerhub_mirror="https://m.example.com")],
    )

    assert client.created_templates == []
    assert client.updated_templates == []
    assert client.deleted_templates == []
