# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the scaleset reconciler."""

import base64
from unittest.mock import MagicMock

from runner_template import RunnerConfig
from scaleset_reconciler import ScalesetReconciler, ScalesetSpec


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _mock_client(providers=None, credentials=None, scalesets=None, templates=None):
    client = MagicMock()
    client.list_providers.return_value = providers or []
    client.list_credentials.return_value = credentials or []
    client.list_scalesets.return_value = scalesets or []
    client.list_templates.return_value = templates or []
    client.create_scaleset.return_value = {"id": "new-uuid", "name": "test"}
    client.update_scaleset.return_value = {"id": "uuid-1", "name": "test"}
    client.create_template.return_value = {"id": 42, "name": "github_linux-my-scaleset"}
    return client


# A minimal system base template GARM seeds; data is base64 like the real API.
_SYSTEM_TEMPLATE = {"id": 1, "name": "github_linux", "data": _b64("#!/bin/bash\nset -e\n")}


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
    runner_config=None,
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
        runner_config=runner_config or RunnerConfig(),
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


# A scaleset carrying runner options copies the system template, creates a
# per-scaleset template, and references it via template_id on create.
def test_create_builds_template_and_sets_template_id():
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[],
        templates=[_SYSTEM_TEMPLATE],
    )
    reconciler = ScalesetReconciler(client)
    spec = _spec(runner_config=RunnerConfig(dockerhub_mirror="https://m.test"))
    reconciler.reconcile([spec])

    client.create_template.assert_called_once()
    created_kwargs = client.create_template.call_args.kwargs
    assert created_kwargs["name"] == "github_linux-my-scaleset"
    assert b"https://m.test" in created_kwargs["data"]
    assert client.create_scaleset.call_args[0][0]["template_id"] == 42


# Without runner options no template is built and the scaleset keeps the default
# template (no template_id in the payload).
def test_no_template_when_runner_config_empty():
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[],
        templates=[_SYSTEM_TEMPLATE],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])

    client.create_template.assert_not_called()
    assert "template_id" not in client.create_scaleset.call_args[0][0]


# An option change refreshes the existing template in place (PUT) without needing
# a scaleset update, since template_id is unchanged.
def test_template_updated_on_content_drift_without_scaleset_update():
    existing_scaleset = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
        "template_id": 7,
    }
    stale_template = {"id": 7, "name": "github_linux-my-scaleset", "data": _b64("#!/bin/bash\n")}
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing_scaleset],
        templates=[_SYSTEM_TEMPLATE, stale_template],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(runner_config=RunnerConfig(dockerhub_mirror="https://m.test"))])

    client.update_template.assert_called_once()
    assert client.update_template.call_args[0][0] == 7
    client.update_scaleset.assert_not_called()


# Deleting an orphaned scaleset also removes its per-scaleset runner template.
def test_orphan_scaleset_deletes_custom_template():
    stale_scaleset = {
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
    stale_template = {"id": 9, "name": "github_linux-stale-scaleset", "data": _b64("x")}
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[stale_scaleset],
        templates=[_SYSTEM_TEMPLATE, stale_template],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([])

    client.delete_scaleset.assert_called_once_with("uuid-stale")
    client.delete_template.assert_called_once_with(9)


# Clearing the runner options reverts the scaleset to GARM's default template
# (template_id -> 0) and removes the now-unreferenced custom template.
def test_template_detached_when_runner_config_cleared():
    existing_scaleset = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
        "template_id": 7,
    }
    custom_template = {"id": 7, "name": "github_linux-my-scaleset", "data": _b64("#!/bin/bash\n")}
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing_scaleset],
        templates=[_SYSTEM_TEMPLATE, custom_template],
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec()])  # default spec has no runner options

    client.update_scaleset.assert_called_once()
    assert client.update_scaleset.call_args[0][1]["template_id"] == 0
    client.delete_template.assert_called_once_with(7)


# A transiently missing system template must not destroy an existing custom
# template: it is kept (no detach, no delete, no rebuild).
def test_existing_custom_template_kept_when_system_template_missing():
    existing_scaleset = {
        "id": "uuid-1",
        "name": "my-scaleset",
        "image_id": "ubuntu-22.04",
        "flavor": "m1.small",
        "max_runners": 5,
        "min_idle_runners": 0,
        "tags": [],
        "runner_group": "default",
        "extra_specs": {},
        "template_id": 7,
    }
    custom_template = {"id": 7, "name": "github_linux-my-scaleset", "data": _b64("#!/bin/bash\n")}
    client = _mock_client(
        providers=[{"name": "openstack-demo"}],
        credentials=[{"name": "github-app-12345"}],
        scalesets=[existing_scaleset],
        templates=[custom_template],  # system github_linux template absent
    )
    reconciler = ScalesetReconciler(client)
    reconciler.reconcile([_spec(runner_config=RunnerConfig(dockerhub_mirror="https://m.test"))])

    client.delete_template.assert_not_called()
    client.update_template.assert_not_called()
    client.update_scaleset.assert_not_called()
