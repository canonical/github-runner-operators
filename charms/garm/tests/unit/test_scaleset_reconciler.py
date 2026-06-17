# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

from unittest.mock import MagicMock, call

from scaleset_reconciler import ScalesetReconciler, ScalesetSpec


def _mock_client(providers=None, scalesets=None, org_id="org-uuid", repo_id=None):
    """Build a mock GarmAuthenticatedClient."""
    client = MagicMock()
    provider_mocks = []
    for name in (providers or []):
        m = MagicMock()
        m.name = name
        provider_mocks.append(m)
    client.list_providers.return_value = provider_mocks

    scaleset_mocks = []
    for ss in (scalesets or []):
        m = MagicMock()
        m.name = ss["name"]
        m.id = ss.get("id", 1)
        m.image = ss.get("image", "ubuntu-22.04")
        m.flavor = ss.get("flavor", "m1.small")
        m.max_runners = ss.get("max_runners", 5)
        m.min_idle_runners = ss.get("min_idle_runners", 0)
        m.runner_group = ss.get("runner_group", None)
        m.extra_specs = ss.get("extra_specs", {})
        scaleset_mocks.append(m)
    client.list_scalesets.return_value = scaleset_mocks

    client.find_org_id.return_value = org_id
    client.find_repo_id.return_value = repo_id
    created = MagicMock()
    created.id = 99
    client.create_org_scaleset.return_value = created
    client.create_repo_scaleset.return_value = created
    updated = MagicMock()
    updated.id = 1
    client.update_scaleset.return_value = updated
    return client


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


def test_create_scaleset_when_not_exists():
    client = _mock_client(providers=["openstack-demo"], scalesets=[])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.create_org_scaleset.assert_called_once()
    args = client.create_org_scaleset.call_args
    assert args[0][0] == "org-uuid"
    params = args[0][1]
    assert params.name == "my-scaleset"
    assert params.image == "ubuntu-22.04"
    assert params.flavor == "m1.small"


def test_skip_creation_when_provider_missing():
    client = _mock_client(providers=[], scalesets=[])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.create_org_scaleset.assert_not_called()
    client.create_repo_scaleset.assert_not_called()


def test_skip_creation_when_entity_not_found():
    client = _mock_client(providers=["openstack-demo"], scalesets=[], org_id=None)
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.create_org_scaleset.assert_not_called()


def test_create_repo_scaleset():
    client = _mock_client(providers=["openstack-demo"], scalesets=[], repo_id="repo-uuid")
    client.find_repo_id.return_value = "repo-uuid"
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(entity_type="repository", entity_name="owner/repo")])
    client.create_repo_scaleset.assert_called_once()
    args = client.create_repo_scaleset.call_args
    assert args[0][0] == "repo-uuid"


def test_update_scaleset_when_image_changed():
    existing = {
        "id": 1,
        "name": "my-scaleset",
        "image": "ubuntu-20.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "runner_group": None,
        "extra_specs": {},
    }
    client = _mock_client(providers=["openstack-demo"], scalesets=[existing])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(image="ubuntu-22.04")])
    client.update_scaleset.assert_called_once()
    args = client.update_scaleset.call_args
    assert args[0][0] == 1
    assert args[0][1].image == "ubuntu-22.04"


def test_no_update_when_scaleset_unchanged():
    existing = {
        "id": 1,
        "name": "my-scaleset",
        "image": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "runner_group": None,
        "extra_specs": {},
    }
    client = _mock_client(providers=["openstack-demo"], scalesets=[existing])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.update_scaleset.assert_not_called()
    client.create_org_scaleset.assert_not_called()


def test_delete_scaleset_not_in_desired():
    existing = {
        "id": 42,
        "name": "stale-scaleset",
        "image": "ubuntu-20.04",
        "flavor": "m1.small",
        "max_runners": 2,
        "min_idle_runners": 0,
        "runner_group": None,
        "extra_specs": {},
    }
    client = _mock_client(providers=["openstack-demo"], scalesets=[existing])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(name="new-scaleset")])
    client.delete_scaleset.assert_called_once_with(42)


def test_existing_scaleset_not_deleted_when_provider_missing():
    """If provider is missing for spec X, scalesets not matching ANY desired name are still deleted,
    but scalesets matching a desired name (even if deferred) are preserved."""
    existing = {
        "id": 1,
        "name": "my-scaleset",
        "image": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "runner_group": None,
        "extra_specs": {},
    }
    client = _mock_client(providers=[], scalesets=[existing])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(name="my-scaleset")])
    client.delete_scaleset.assert_not_called()


def test_no_delete_when_desired_is_empty_and_no_observed():
    client = _mock_client(providers=[], scalesets=[])
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([])
    client.delete_scaleset.assert_not_called()


def test_pre_install_scripts_included_in_create():
    client = _mock_client(providers=["openstack-demo"], scalesets=[])
    reconciler = ScalesetReconciler(client)
    scripts = {"setup.sh": "#!/bin/bash\napt-get update"}
    reconciler.reconcile([_spec(pre_install_scripts=scripts)])
    params = client.create_org_scaleset.call_args[0][1]
    assert params.extra_specs == {"pre_install_scripts": scripts}
