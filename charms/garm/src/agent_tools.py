# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Publishes the garm-agent binaries built into the rock to GARM's tool store.

When agent mode is enabled on an entity, GARM hands each runner a download URL for the
garm-agent binary matching the runner's OS and architecture. It resolves that URL by
searching its object store for tags ``category=garm-agent``, ``os_type=<os>`` and
``os_arch=<arch>``; if nothing matches it falls back to a github.com release URL. This
module keeps the store stocked from the binaries the rock ships, so that fallback is never
reached and runners only ever download from GARM itself.

The sync is a compare-and-swap against the sha256 GARM records for each stored tool: the
rock ships a small manifest of per-architecture digests, so a converged deployment
transfers about a kilobyte per reconcile and only reads binary bytes out of the workload
container for architectures that actually differ. Replacement is atomic from a runner's
point of view because GARM's upload endpoint deletes the superseded tool itself, only once
the new one is stored.
"""

import hashlib
import logging

import ops

from garm_api import GarmAuthenticatedClient

logger = logging.getLogger(__name__)

AGENT_DIR = "/opt/garm-agent"
MANIFEST_PATH = f"{AGENT_DIR}/manifest.txt"


class AgentToolsError(Exception):
    """The garm-agent binaries could not be published to GARM."""


def ensure_agent_tools(client: GarmAuthenticatedClient, container: ops.Container) -> str:
    """Make GARM's tool store match the garm-agent binaries shipped in the rock.

    Args:
        client: Authenticated GARM API client.
        container: The workload container, which holds the binaries and the manifest.

    Returns:
        The garm-agent version now published for every architecture the rock ships.

    Raises:
        AgentToolsError: If the rock ships no usable manifest, or a binary named by the
            manifest is missing from the container.
        GarmApiError: If GARM rejects a listing or an upload. Agent mode must stay off in
            that case, so the failure is not swallowed here.
    """
    version, digests = _read_manifest(container)
tools_per_arch = {tool.os_arch: tool for tool in client.list_agent_tools()}

    for arch in sorted(digests):
        current = stored.get(arch)
        if (
            current is not None
            and current.sha256sum == digests[arch]
            and current.version == version
        ):
            continue
        _upload_agent_tool(client, container, arch, digests[arch], version)
        logger.info("Published garm-agent %s for linux/%s", version, arch)
    return version


def _read_manifest(container: ops.Container) -> tuple[str, dict[str, str]]:
    """Read the version and per-architecture digests the rock recorded at build time.

    Args:
        container: The workload container the rock's manifest lives in.

    Returns:
        The agent version and a mapping of GARM architecture name to sha256 hex digest.

    Raises:
        AgentToolsError: If the manifest is absent, unreadable, including when the
            workload container is not up yet, or lists no architecture.
    """
    try:
        manifest = container.pull(MANIFEST_PATH).read()
    except ops.pebble.Error as exc:
        raise AgentToolsError(
            f"garm-agent manifest unavailable at {MANIFEST_PATH}: {exc}"
        ) from exc

    version = ""
    digests: dict[str, str] = {}
    for line in manifest.splitlines():
        key, _, value = line.strip().partition(" ")
        if not value:
            continue
        if key == "version":
            version = value
        else:
            digests[key] = value
    if not version or not digests:
        raise AgentToolsError(f"garm-agent manifest at {MANIFEST_PATH} is malformed")
    return version, digests


def _upload_agent_tool(
    client: GarmAuthenticatedClient,
    container: ops.Container,
    arch: str,
    digest: str,
    version: str,
) -> None:
    """Upload one architecture's binary from the rock to GARM.

    Args:
        client: Authenticated GARM API client.
        container: The workload container holding the binary.
        arch: GARM architecture name.
        digest: The sha256 the rock recorded, verified against the bytes actually read.
        version: The agent version to publish the binary under.

    Raises:
        AgentToolsError: If the binary is missing from the container or its content does
            not match the manifest, which would leave GARM serving runners a binary the
            charm cannot later recognise as current.
        GarmApiError: If GARM rejects the upload.
    """
    path = f"{AGENT_DIR}/linux/{arch}/garm-agent"
    try:
        content = container.pull(path, encoding=None).read()
    except ops.pebble.Error as exc:
        raise AgentToolsError(f"garm-agent binary unavailable at {path}: {exc}") from exc
    if hashlib.sha256(content).hexdigest() != digest:
        raise AgentToolsError(f"garm-agent binary at {path} does not match the manifest digest")

    client.upload_agent_tool(
        name=f"garm-agent-linux-{arch}",
        description=f"garm-agent {version} for linux/{arch}, built into the GARM rock",
        os_arch=arch,
        version=version,
        content=content,
    )
