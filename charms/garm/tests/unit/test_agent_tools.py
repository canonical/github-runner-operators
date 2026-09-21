# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for agent_tools.py."""

import hashlib
import io
from unittest.mock import MagicMock

import ops
import pytest

from agent_tools import AgentToolsError, ensure_agent_tools
from garm_api import GarmApiError
from garm_client.models.file_object import FileObject
from garm_client.models.garm_agent_tools_paginated_response_results_inner import (
    GARMAgentToolsPaginatedResponseResultsInner,
)

_BINARIES = {"amd64": b"\x7fELF amd64", "arm64": b"\x7fELF arm64"}
_DIGESTS = {arch: hashlib.sha256(data).hexdigest() for arch, data in _BINARIES.items()}
_VERSION = "v0.1.1"


def _container(manifest: str | None = None, binaries: dict[str, bytes] | None = None):
    """A workload container serving the rock's manifest and binaries over Pebble."""
    if manifest is None:
        manifest = "\n".join(
            [f"version {_VERSION}"] + [f"{arch} {digest}" for arch, digest in _DIGESTS.items()]
        )
    files = {"/opt/garm-agent/manifest.txt": manifest}
    for arch, data in (_BINARIES if binaries is None else binaries).items():
        files[f"/opt/garm-agent/linux/{arch}/garm-agent"] = data

    def pull(path, encoding="utf-8"):
        if path not in files:
            raise ops.pebble.PathError("not-found", path)
        content = files[path]
        return io.StringIO(content) if encoding else io.BytesIO(content)

    container = MagicMock()
    container.pull.side_effect = pull
    return container


def _client(stored: list[GARMAgentToolsPaginatedResponseResultsInner] | None = None):
    """A GARM client already storing *stored*."""
    client = MagicMock()
    client.list_agent_tools.return_value = stored or []
    client.upload_agent_tool.side_effect = lambda **kwargs: FileObject(
        id=100, name=kwargs["name"], sha256=hashlib.sha256(kwargs["content"]).hexdigest()
    )
    return client


def _stored_tools(arch: str, sha256: str, version: str = _VERSION):
    """A stored agent tool as GARM lists it back."""
    return GARMAgentToolsPaginatedResponseResultsInner(
        id=1,
        name=f"garm-agent-linux-{arch}",
        os_type="linux",
        os_arch=arch,
        sha256sum=sha256,
        version=version,
    )


def test_every_architecture_is_published_when_garm_stores_none():
    """
    arrange: A GARM storing no agent tools and a workload shipping two architectures.
    act: Ensure the agent tools.
    assert: Both binaries are uploaded, each under the architecture GARM matches a runner
        against and the version it refuses to serve a tool without.
    """
    client = _client()

    version = ensure_agent_tools(client, _container())

    assert version == _VERSION
    uploaded = {
        call.kwargs["os_arch"]: call.kwargs["content"]
        for call in client.upload_agent_tool.call_args_list
    }
    assert uploaded == _BINARIES
    assert {call.kwargs["version"] for call in client.upload_agent_tool.call_args_list} == {
        _VERSION
    }


def test_matching_digests_upload_nothing():
    """
    arrange: A GARM already storing both architectures at the rock's digests and version.
    act: Ensure the agent tools.
    assert: Nothing is uploaded, and no binary is even read out of the container, so a
        converged deployment costs one listing and a kilobyte of manifest per reconcile.
    """
    client = _client([_stored(arch, digest) for arch, digest in _DIGESTS.items()])
    container = _container()

    ensure_agent_tools(client, container)

    client.upload_agent_tool.assert_not_called()
    assert container.pull.call_args_list == [(("/opt/garm-agent/manifest.txt",), {})]


@pytest.mark.parametrize(
    "stale",
    [
        _stored("amd64", "0" * 64),
        _stored("amd64", _DIGESTS["amd64"], version="v0.0.1"),
    ],
    ids=["different-binary", "different-version"],
)
def test_a_tool_that_differs_from_the_rock_is_replaced(stale):
    """
    arrange: A GARM storing a tool for one architecture that disagrees with the rock, as an
        agent upgrade shipped in a new rock revision leaves it.
    act: Ensure the agent tools.
    assert: Only that architecture is re-uploaded. GARM's upload endpoint drops the tool it
        supersedes itself, so the charm never has to open a window with nothing stored — the
        one window in which GARM would hand a runner a github.com download URL instead.
    """
    client = _client([stale, _stored("arm64", _DIGESTS["arm64"])])

    ensure_agent_tools(client, _container())

    client.upload_agent_tool.assert_called_once()
    assert client.upload_agent_tool.call_args.kwargs["os_arch"] == "amd64"
    assert client.upload_agent_tool.call_args.kwargs["content"] == _BINARIES["amd64"]


@pytest.mark.parametrize(
    "error",
    [
        ops.pebble.PathError("not-found", "/opt/garm-agent/manifest.txt"),
        ops.pebble.ConnectionError("socket not found"),
    ],
    ids=["absent", "container-down"],
)
def test_an_unreadable_manifest_is_reported(error):
    """
    arrange: A workload container with no manifest — as a rock revision predating agent mode
        has — or one that is not up yet.
    act: Ensure the agent tools.
    assert: AgentToolsError is raised, so the charm leaves agent mode alone instead of enabling
        it with nothing to serve.
    """
    container = _container()
    container.pull.side_effect = error

    with pytest.raises(AgentToolsError):
        ensure_agent_tools(_client(), container)


@pytest.mark.parametrize(
    "manifest",
    ["amd64 abc", f"version {_VERSION}", ""],
    ids=["no-version", "no-architecture", "empty"],
)
def test_a_malformed_manifest_is_reported(manifest: str):
    """
    arrange: A manifest missing the version, missing every architecture, or empty.
    act: Ensure the agent tools.
    assert: AgentToolsError is raised rather than silently publishing a partial set.
    """
    with pytest.raises(AgentToolsError):
        ensure_agent_tools(_client(), _container(manifest=manifest))


def test_a_binary_that_does_not_match_the_manifest_is_rejected():
    """
    arrange: A manifest whose digest disagrees with the binary beside it.
    act: Ensure the agent tools.
    assert: AgentToolsError is raised and nothing is uploaded — a binary stored under a digest
        the charm cannot reproduce would be re-uploaded on every single reconcile.
    """
    client = _client()

    with pytest.raises(AgentToolsError):
        ensure_agent_tools(client, _container(binaries={"amd64": b"tampered", "arm64": b"other"}))

    client.upload_agent_tool.assert_not_called()


def test_a_missing_binary_is_reported():
    """
    arrange: A manifest naming an architecture whose binary is absent from the container.
    act: Ensure the agent tools.
    assert: AgentToolsError is raised.
    """
    with pytest.raises(AgentToolsError):
        ensure_agent_tools(_client(), _container(binaries={"amd64": _BINARIES["amd64"]}))


def test_an_upload_failure_is_propagated():
    """
    arrange: A GARM storing no agent tools that rejects the upload.
    act: Ensure the agent tools.
    assert: GarmApiError reaches the caller, so the charm waits and retries rather than
        enabling agent mode against a GARM that has no binary to serve.
    """
    client = _client()
    client.upload_agent_tool.side_effect = GarmApiError("boom")

    with pytest.raises(GarmApiError):
        ensure_agent_tools(client, _container())
