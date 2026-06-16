# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

from unittest.mock import MagicMock

from scaleset_reconciler import ScalesetReconciler, ScalesetSpec


def _mock_client(providers=None, credentials=None, scalesets=None):
    client = MagicMock()
    client.list_providers.return_value = providers or []
    client.list_credentials.return_value = credentials or []
    client.list_scalesets.return_value = scalesets or []
    client.create_scaleset.return_value = {"id": "new-uuid", "name": "test"}
    client.update_scaleset.return_value = {"id": "uuid-1", "name": "test"}
    return client


def _spec(
    name="my-scaleset",
    provider_name="openstack-demo",
    credentials_name="github-app-12345",
    image_id="ubuntu-22.04",
    flavor="m1.small",
    os_arch="x64",
    min_idle=0,
    max_runners=5,
    labels=None,
    runner_group="default",
    pre_install_scripts=None,
):
    return ScalesetSpec(
        name=name,
        provider_name=provider_name,
        credentials_name=credentials_name,
        image_id=image_id,
        flavor=flavor,
        os_arch=os_arch,
        min_idle_runners=min_idle,
        max_runners=max_runners,
        labels=labels or [],
        runner_group=runner_group,
        pre_install_scripts=pre_install_scripts or {},
    )


def test_create_scaleset_when_not_exists():
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.create_scaleset.assert_called_once()
    call_payload = client.create_scaleset.call_args[0][0]
    assert call_payload["name"] == "my-scaleset"
    assert call_payload["image_id"] == "ubuntu-22.04"
    assert call_payload["flavor"] == "m1.small"


def test_skip_creation_when_provider_missing():
    client = _mock_client(
        providers=[],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.create_scaleset.assert_not_called()


def test_skip_creation_when_credential_missing():
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[],
        scalesets=[],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.create_scaleset.assert_not_called()


def test_update_scaleset_when_image_changed():
    existing = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-20.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
    }
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(image_id="ubuntu-22.04")])
    client.update_scaleset.assert_called_once()
    args = client.update_scaleset.call_args
    assert args[0][0] == "uuid-1"
    assert args[0][1]["image_id"] == "ubuntu-22.04"


def test_no_update_when_scaleset_unchanged():
    existing = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
    }
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.update_scaleset.assert_not_called()
    client.create_scaleset.assert_not_called()


def test_delete_scaleset_not_in_desired():
    existing = {
        "id": "uuid-stale",
        "name": "stale-scaleset",
        "image_id": "ubuntu-20.04",
        "flavor": "m1.small",
        "max_runners": 2,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
    }
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(name="new-scaleset")])
    client.delete_scaleset.assert_called_once_with("uuid-stale")


def test_no_delete_when_desired_is_empty():
    client = _mock_client(
        providers=[],
        credentials=[],
        scalesets=[],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([])
    client.delete_scaleset.assert_not_called()


def test_pre_install_scripts_included_in_create():
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[],
    )
    reconciler = ScalesetReconciler(client)
    scripts = {"setup.sh": "#!/bin/bash\napt-get update"}
    reconciler.reconcile([_spec(pre_install_scripts=scripts)])
    payload = client.create_scaleset.call_args[0][0]
    assert payload["extra_specs"]["pre_install_scripts"] == scripts


def test_existing_scaleset_not_deleted_when_provider_temporarily_missing():
    existing = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
    }
    client = _mock_client(
        providers=[],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])
    client.delete_scaleset.assert_not_called()
    client.create_scaleset.assert_not_called()

    existing = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": ["z-tag", "a-tag"],
        "runner_group": "default",
        "extra_specs": {},
    }
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(labels=["a-tag", "z-tag"])])
    client.update_scaleset.assert_not_called()
