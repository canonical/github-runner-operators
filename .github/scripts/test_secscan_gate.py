# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for secscan_gate, driven through a fake ``secscan-client`` on PATH."""

import importlib.util
import pathlib
import stat

import pytest
import yaml

_SPEC = importlib.util.spec_from_file_location(
    "secscan_gate", pathlib.Path(__file__).with_name("secscan_gate.py")
)
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)

# The token is the fake client's stdin, so it selects the exit code.
FAKE_CLIENT = """#!/usr/bin/env bash
tok=$(cat); echo "args=$* token=$tok"
case "$tok" in clean) exit 0;; stale) exit 101;; cves) exit 150;; *) exit 3;; esac
"""


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A repo-like cwd with a fake client on PATH; returns a helper to lay out gate inputs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    client = bin_dir / "secscan-client"
    client.write_text(FAKE_CLIENT)
    client.chmod(client.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}:{pathlib.os.environ['PATH']}")
    monkeypatch.setenv("SECSCAN_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github" / "secscan-exclusions").mkdir(parents=True)
    (tmp_path / "scanner").mkdir()

    def setup(manifest: list[str], state: dict) -> pathlib.Path:
        manifest_doc = {"artifacts": [{"name": n} for n in manifest]}
        (tmp_path / ".github" / "sbomber-manifest.yaml").write_text(yaml.safe_dump(manifest_doc))
        (tmp_path / "scanner" / ".statefile.yaml").write_text(yaml.safe_dump(state))
        return tmp_path

    return setup


def _artifact(name: str, token: str | None) -> dict:
    entry = {"name": name}
    if token:
        entry["processing"] = {"secscan": {"token": token}}
    return entry


def test_gate_passes_when_every_artifact_is_clean(workspace, capsys):
    """
    arrange: a statefile with two clean artifacts that match the manifest.
    act: run the gate.
    assert: exit 0, each artifact reported clean and its result file written.
    """
    root = workspace(["a", "b"], {"artifacts": [_artifact("a", "clean"), _artifact("b", "clean")]})

    assert gate.main() == 0

    out = capsys.readouterr().out
    assert "a: No CVEs found." in out and "b: No CVEs found." in out
    assert (root / "scanner" / "reports" / "a.result.txt").is_file()


def test_gate_stages_only_active_exclusions(workspace):
    """
    arrange: artifact a has an active exclusion, b only comments, c has no file.
    act: run the gate.
    assert: only a is passed --exclusions-filename, pointing at a staged copy.
    """
    root = workspace(
        ["a", "b", "c"],
        {"artifacts": [_artifact(n, "clean") for n in "abc"]},
    )
    exclusions = root / ".github" / "secscan-exclusions"
    (exclusions / "a.txt").write_text("# why\nCVE-1\n")
    (exclusions / "b.txt").write_text("# only a comment\n\n")

    assert gate.main() == 0

    reports = root / "scanner" / "reports"
    assert f"--exclusions-filename {root}/exclusions-a.txt" in (reports / "a.result.txt").read_text()
    assert "--exclusions-filename" not in (reports / "b.result.txt").read_text()
    assert "--exclusions-filename" not in (reports / "c.result.txt").read_text()
    assert (root / "exclusions-a.txt").read_text() == "# why\nCVE-1\n"


@pytest.mark.parametrize(
    "token, expected",
    [
        ("stale", "::error::a: Excluded CVEs are no longer reported"),
        ("cves", "::error::a: CVEs found"),
        ("broken", "::error::a: secscan-client failed (exit 3)"),
        (None, "::error::a: no secscan token"),
    ],
)
def test_gate_fails_on_non_clean_results(workspace, capsys, token, expected):
    """
    arrange: one artifact whose client exit code is 101, 1xx, another error, or no token.
    act: run the gate.
    assert: exit 1 with the matching classification.
    """
    workspace(["a"], {"artifacts": [_artifact("a", token)]})

    assert gate.main() == 1

    assert expected in capsys.readouterr().out


@pytest.mark.parametrize(
    "state, expected",
    [
        ({}, "sbomber statefile has no artifacts"),
        ({"artifacts": []}, "sbomber statefile has no artifacts"),
        ({"artifacts": [_artifact("a", "clean")]}, "::error::b: missing from the sbomber statefile"),
    ],
)
def test_gate_fails_when_manifest_artifacts_were_not_scanned(workspace, capsys, state, expected):
    """
    arrange: a statefile that is empty or lacks manifest artifact b.
    act: run the gate.
    assert: exit 1 naming the problem, so an unscanned artifact can never pass silently.
    """
    workspace(["a", "b"], state)

    assert gate.main() == 1

    assert expected in capsys.readouterr().out
