# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Unit tests for the charm-source resolution helpers in ``tests.integration.conftest``.

These decide whether the end-to-end suite deploys a locally built charm or a published
Charmhub revision. Getting it wrong is silent -- the suite still goes green, having
tested an artifact nobody asked for -- and the only end-to-end check costs two hours on
a private-endpoint runner, so the resolution is pinned down here instead.
"""

import pytest

from tests.integration.conftest import (
    CHARM_CHANNEL_ENV_VAR,
    charm_deploy_kwargs,
    charmhub_revision,
)


@pytest.mark.parametrize(
    "charm_name, env_var",
    [
        ("garm", "E2E_GARM_REVISION"),
        ("garm-configurator", "E2E_GARM_CONFIGURATOR_REVISION"),
    ],
)
def test_charmhub_revision_reads_the_per_charm_variable(monkeypatch, charm_name, env_var):
    """
    arrange: A channel plus the revision variable belonging to one charm.
    act: Resolve the revision for that charm.
    assert: The variable named after the charm is the one read, so the two charms can
        be pinned to different revisions in the same run.
    """
    monkeypatch.setenv(CHARM_CHANNEL_ENV_VAR, "latest/edge")
    monkeypatch.setenv(env_var, "114")

    assert charmhub_revision(charm_name) == 114


def test_charmhub_revision_is_none_without_an_override(monkeypatch):
    """
    arrange: Neither the channel nor any revision variable is set.
    act: Resolve the revision for both charms.
    assert: Both are None, so an unconfigured run keeps building charms locally.
    """
    monkeypatch.delenv(CHARM_CHANNEL_ENV_VAR, raising=False)
    monkeypatch.delenv("E2E_GARM_REVISION", raising=False)
    monkeypatch.delenv("E2E_GARM_CONFIGURATOR_REVISION", raising=False)

    assert charmhub_revision("garm") is None
    assert charmhub_revision("garm-configurator") is None


@pytest.mark.parametrize("value", ["", "   "])
def test_charmhub_revision_treats_blank_as_unset(monkeypatch, value):
    """
    arrange: A revision variable set to an empty or whitespace-only value.
    act: Resolve the revision.
    assert: It is None rather than an error, because a workflow input that was left
        blank arrives as an empty string rather than an absent variable.
    """
    monkeypatch.setenv(CHARM_CHANNEL_ENV_VAR, "latest/edge")
    monkeypatch.setenv("E2E_GARM_REVISION", value)

    assert charmhub_revision("garm") is None


def test_charmhub_revision_rejects_a_revision_without_a_channel(monkeypatch):
    """
    arrange: A revision variable set while the channel variable is missing.
    act: Resolve the revision.
    assert: It raises, because deploying a revision needs a channel and silently
        falling back to a locally built charm would test the wrong artifact.
    """
    monkeypatch.delenv(CHARM_CHANNEL_ENV_VAR, raising=False)
    monkeypatch.setenv("E2E_GARM_REVISION", "114")

    with pytest.raises(ValueError, match=CHARM_CHANNEL_ENV_VAR):
        charmhub_revision("garm")


def test_charmhub_revision_rejects_a_non_integer(monkeypatch):
    """
    arrange: A revision variable holding something that is not a number.
    act: Resolve the revision.
    assert: It raises naming the offending value, rather than failing later inside
        juju deploy where the cause is far less obvious.
    """
    monkeypatch.setenv(CHARM_CHANNEL_ENV_VAR, "latest/edge")
    monkeypatch.setenv("E2E_GARM_REVISION", "latest")

    with pytest.raises(ValueError, match="must be an integer"):
        charmhub_revision("garm")


def test_charm_deploy_kwargs_drops_resources_for_charmhub(monkeypatch):
    """
    arrange: A channel and revision pinning the GARM charm to Charmhub, and a locally
        built OCI image that would otherwise be attached.
    act: Build the deploy kwargs.
    assert: The channel and revision are passed and the resources are dropped, because
        a published revision carries its own images and attaching a local build would
        deploy a different artifact than the one being promoted.
    """
    monkeypatch.setenv(CHARM_CHANNEL_ENV_VAR, "latest/edge")
    monkeypatch.setenv("E2E_GARM_REVISION", "114")

    kwargs = charm_deploy_kwargs("garm", {"app-image": "localhost:32000/garm:latest"})

    assert kwargs == {"channel": "latest/edge", "revision": 114}


def test_charm_deploy_kwargs_keeps_resources_when_building_locally(monkeypatch):
    """
    arrange: No override, and a locally built OCI image.
    act: Build the deploy kwargs.
    assert: The image is still attached as a resource, so the default path is
        unchanged for the pull-request integration suites.
    """
    monkeypatch.delenv(CHARM_CHANNEL_ENV_VAR, raising=False)
    monkeypatch.delenv("E2E_GARM_REVISION", raising=False)

    kwargs = charm_deploy_kwargs("garm", {"app-image": "localhost:32000/garm:latest"})

    assert kwargs == {"resources": {"app-image": "localhost:32000/garm:latest"}}


def test_charm_deploy_kwargs_omits_empty_resources(monkeypatch):
    """
    arrange: No override and no resources, as for the resource-less configurator charm.
    act: Build the deploy kwargs.
    assert: No resources key is produced, so juju deploy is called exactly as before.
    """
    monkeypatch.delenv(CHARM_CHANNEL_ENV_VAR, raising=False)
    monkeypatch.delenv("E2E_GARM_CONFIGURATOR_REVISION", raising=False)

    assert charm_deploy_kwargs("garm-configurator") == {}
