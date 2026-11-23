"""Throwaway: run the garm charm's own GARM code against the harness GARM.

Points the github.com endpoint at the charm's default runner tools URL with the
charm's GarmAuthenticatedClient, and publishes the rock's garm-agent binaries
with the charm's ensure_agent_tools, the same calls the charm makes in its
reconcile. Only the Juju side is missing: the workload container is a local
directory holding what the rock's garm-agent part installed.

Usage: charm_steps.py <garm api base url> <admin password file> <rock install root>
"""

import logging
import pathlib
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "charms/garm/src"))

from agent_tools import ensure_agent_tools  # noqa: E402
from garm_api import GarmAuthenticatedClient  # noqa: E402
from github_reconciler import DEFAULT_GITHUB_ENDPOINT  # noqa: E402


class _LocalContainer:
    """Serves files from the rock's install root, as the workload container would."""

    def __init__(self, root: pathlib.Path) -> None:
        self._root = root

    def pull(self, path: str, *, encoding: str | None = "utf-8"):
        file = self._root / path.lstrip("/")
        return file.open("rb") if encoding is None else file.open(encoding=encoding)


def main() -> None:
    base_url, password_file, rock_root = sys.argv[1:]
    logging.basicConfig(level=logging.INFO)

    charmcraft = yaml.safe_load((REPO / "charms/garm/charmcraft.yaml").read_text())
    url = charmcraft["config"]["options"]["runner-tools-metadata-url"]["default"]

    client = GarmAuthenticatedClient.from_login(
        base_url, "admin", pathlib.Path(password_file).read_text()
    )
    client.set_tools_metadata_url(DEFAULT_GITHUB_ENDPOINT, url)
    print(f"Set the {DEFAULT_GITHUB_ENDPOINT} tools metadata URL to the charm default {url}")

    version = ensure_agent_tools(client, _LocalContainer(pathlib.Path(rock_root)))
    published = sorted(tool.os_arch for tool in client.list_agent_tools())
    print(f"Published garm-agent {version} for {published}")
    if "s390x" not in published:
        sys.exit("::error::the charm did not publish an s390x garm-agent")


if __name__ == "__main__":
    main()
