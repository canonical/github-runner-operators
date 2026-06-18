# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

import pytest

from scaleset_reconciler import ScalesetReconciler, ScalesetSpec


# ---------------------------------------------------------------------------
# Fake client — records operations as observable state
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, name):
        self.name = name


class _FakeScaleset:
    def __init__(self, name, sid=1, image="ubuntu-22.04", flavor="m1.small",
                 max_runners=5, min_idle_runners=0, runner_group=None, extra_specs=None):
        self.name = name
        self.id = sid
        self.image = image
        self.flavor = flavor
        self.max_runners = max_runners
        self.min_idle_runners = min_idle_runners
        self.runner_group = runner_group
        self.extra_specs = extra_specs or {}


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
                runner_group=ss.get("runner_group", None),
                extra_specs=ss.get("extra_specs", {}),
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    )


def _reconcile(client, desired):
    ScalesetReconciler(client).reconcile(desired)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entity_type, entity_name, create_key, expected_entity_id",
    [
        ("organization", "my-org", "org", "org-uuid"),
        ("repository", "owner/repo", "repo", "repo-uuid"),
    ],
    ids=["org-entity", "repo-entity"],
)
def test_create_scaleset(entity_type, entity_name, create_key, expected_entity_id):
    """A scaleset absent from GARM is created under the correct entity."""
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
    """Creation is deferred (not attempted) when provider or entity is absent."""
    client = FakeGarmClient(providers=providers, scalesets=[], org_id=org_id)
    _reconcile(client, [_spec()])

    assert client.created == []
    assert client.updated == []
    assert client.deleted == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def _existing_scaleset(**overrides):
    base = dict(name="my-scaleset", id=1, image="ubuntu-22.04", flavor="m1.small",
                max_runners=5, min_idle_runners=0, runner_group=None, extra_specs={})
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "changed_field, new_value, spec_kwarg",
    [
        ("image", "ubuntu-24.04", {"image": "ubuntu-24.04"}),
        ("flavor", "m1.large", {"flavor": "m1.large"}),
        ("max_runners", 10, {"max_runners": 10}),
        ("min_idle_runners", 2, {"min_idle": 2}),
    ],
    ids=["image-changed", "flavor-changed", "max-runners-changed", "min-idle-changed"],
)
def test_update_when_field_changed(changed_field, new_value, spec_kwarg):
    """An existing scaleset is updated when any tracked field differs."""
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset()],
    )
    _reconcile(client, [_spec(**spec_kwarg)])

    assert len(client.updated) == 1
    scaleset_id, params = client.updated[0]
    assert scaleset_id == 1
    assert client.created == []
    assert client.deleted == []


def test_no_update_when_scaleset_unchanged():
    """An existing scaleset that matches the desired state is left untouched."""
    client = FakeGarmClient(
        providers=["openstack-demo"],
        scalesets=[_existing_scaleset()],
    )
    _reconcile(client, [_spec()])

    assert client.created == []
    assert client.updated == []
    assert client.deleted == []


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_orphaned_scaleset():
    """A scaleset not in the desired set is deleted."""
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
    """No scalesets are deleted when state is empty or the spec is deferred."""
    client = FakeGarmClient(providers=providers, scalesets=scalesets)
    _reconcile(client, desired)

    assert client.deleted == expected_deleted


# ---------------------------------------------------------------------------
# Extra specs (pre_install_scripts)
# ---------------------------------------------------------------------------


def test_pre_install_scripts_passed_in_create():
    """pre_install_scripts are included in extra_specs when creating a scaleset."""
    scripts = {"setup.sh": "#!/bin/bash\napt-get update"}
    client = FakeGarmClient(providers=["openstack-demo"], scalesets=[])
    _reconcile(client, [_spec(pre_install_scripts=scripts)])

    assert len(client.created) == 1
    _, _, params = client.created[0]
    assert params.extra_specs == {"pre_install_scripts": scripts}
