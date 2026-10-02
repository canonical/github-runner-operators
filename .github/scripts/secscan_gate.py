# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fail CI when any sbomber-submitted secscan result has unexcluded CVEs.

sbomber only reports whether a scan ran, not what it found, so this re-reads each
artifact's result through `secscan-client --batch`, whose exit code encodes findings.
"""

import os
import pathlib
import subprocess
import sys

import yaml

MANIFEST = pathlib.Path(".github/sbomber-manifest.yaml")
STATEFILE = pathlib.Path("scanner/.statefile.yaml")
REPORTS = pathlib.Path("scanner/reports")
EXCLUSIONS = pathlib.Path(".github/secscan-exclusions")


def main() -> int:
    state = yaml.safe_load(STATEFILE.read_text())
    REPORTS.mkdir(parents=True, exist_ok=True)
    artifacts = state.get("artifacts") or []
    failed = False
    if not artifacts:
        print("::error::sbomber statefile has no artifacts; prepare or submit failed, re-run the job.")
        failed = True
    # A dropped artifact would otherwise go unscanned and pass silently.
    expected = [a["name"] for a in yaml.safe_load(MANIFEST.read_text())["artifacts"]]
    present = {a["name"] for a in artifacts}
    for name in expected:
        if name not in present:
            print(f"::error::{name}: missing from the sbomber statefile; it was not scanned, re-run the job.")
            failed = True
    for artifact in artifacts:
        name = artifact["name"]
        token = ((artifact.get("processing") or {}).get("secscan") or {}).get("token")
        if not token:
            print(f"::error::{name}: no secscan token; submission failed, re-run the job.")
            failed = True
            continue
        proc = subprocess.run(
            ["secscan-client", "--batch", "result", *_exclusion_args(name)],
            input=token, text=True, capture_output=True, check=False,
        )
        (REPORTS / f"{name}.result.txt").write_text(proc.stdout + proc.stderr)
        print(_classify(name, proc.returncode))
        failed = failed or proc.returncode != 0
    return 1 if failed else 0


def _exclusion_args(name: str) -> list[str]:
    src = EXCLUSIONS / f"{name}.txt"
    if not src.is_file():
        return []
    active = [l for l in src.read_text().splitlines() if l.strip() and not l.strip().startswith("#")]
    if not active:
        return []
    # The snap can only read files under its own common directory.
    staged = pathlib.Path(os.environ["SECSCAN_DIR"]) / f"exclusions-{name}.txt"
    staged.write_text(src.read_text())
    return ["--exclusions-filename", str(staged)]


def _classify(name: str, rc: int) -> str:
    if rc == 0:
        return f"{name}: No CVEs found."
    if rc == 101:
        return f"::error::{name}: Excluded CVEs are no longer reported; remove them from .github/secscan-exclusions/."
    if 100 <= rc <= 199:
        return f"::error::{name}: CVEs found; download the secscan report artifact and triage per SECURITY.md."
    return f"::error::{name}: secscan-client failed (exit {rc}); re-run the job."


if __name__ == "__main__":
    sys.exit(main())
