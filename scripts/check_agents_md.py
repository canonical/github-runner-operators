#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Guard against rot in the AGENTS.md guidance files.

AGENTS.md files cite source files, private methods, and tox environments by name.
Those citations silently go stale when code is renamed or moved. This script
re-validates every machine-checkable citation so CI fails loudly instead.

It deliberately checks only citation kinds that are unambiguous (near-zero false
positives); prose, bare filenames, and public/library symbol names are left to
human review. Checked kinds, all written inside `backticks`:

* paths      — explicit relative paths (contain "/", end in a known extension or
               a trailing "/"), e.g. `src/charm.py`, `cmd/planner/`. Bare
               filenames, globs, and absolute paths are skipped as too ambiguous.
* methods    — leading-underscore identifiers (our private charm methods), e.g.
               `_reconcile`, `_create_app`; verified to exist as a `def`.
* tox envs   — `tox -e <name>`; verified against tox.ini.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRST_PARTY = ("charms", "cmd", "internal")
# "tests" is excluded so a private-method citation can't be satisfied by a
# same-named helper in a test file when the real charm method is renamed/removed.
EXCLUDE_DIRS = {".git", ".tox", "lib", "parts", "prime", "stage", "vendor", "build", "tests"}

PATH_EXTENSIONS = ("py", "go", "toml", "yaml", "yml", "ini", "md", "cfg", "txt")
BACKTICK = re.compile(r"`([^`]+)`")
TOX_ENV = re.compile(r"tox -e ([\w-]+)")
PRIVATE_METHOD = re.compile(r"^_[a-z]\w*$")


def main() -> int:
    """Validate citations in every first-party AGENTS.md and report breakage."""
    tox_envs = _collect_tox_envs()
    errors: list[str] = []
    for agents_md in sorted(REPO_ROOT.rglob("AGENTS.md")):
        if _excluded(agents_md):
            continue
        errors.extend(_check_file(agents_md, tox_envs))

    if errors:
        print("Broken citations in AGENTS.md files:\n")
        print("\n".join(errors))
        print(f"\n{len(errors)} broken citation(s). Update the AGENTS.md or the code.")
        return 1
    print("AGENTS.md citations OK.")
    return 0


def _check_file(agents_md: Path, tox_envs: set[str]) -> list[str]:
    """Return one error string per broken citation in a single AGENTS.md."""
    rel = agents_md.relative_to(REPO_ROOT)
    text = agents_md.read_text(encoding="utf-8")
    errors: list[str] = []

    for env in TOX_ENV.findall(text):
        if env not in tox_envs:
            errors.append(f"{rel}: unknown tox env `tox -e {env}`")

    # Per-charm files cite paths relative to their own dir; the root file cites
    # them relative to the repo. Resolve against both. A private method is
    # accepted if it exists anywhere in first-party code: this catches a full
    # rename/removal while tolerating `_reconcile`, which the paas-charm files
    # name only to warn against adding one (it lives in garm-configurator).
    path_roots = [agents_md.parent, REPO_ROOT]
    method_roots = [REPO_ROOT / d for d in FIRST_PARTY]

    for token in {t.strip() for t in BACKTICK.findall(text)}:
        if _is_path(token):
            if ".." in token.split("/"):
                errors.append(f"{rel}: path `{token}` must be repo-relative (no '..')")
            elif not any((root / token.rstrip("/")).exists() for root in path_roots):
                errors.append(f"{rel}: path `{token}` does not exist")
            continue
        method = _private_method(token)
        if method and not _defines_method(method_roots, method):
            errors.append(f"{rel}: no `def {method}` found for citation `{token}`")
    return errors


def _is_path(token: str) -> bool:
    """True only for explicit relative paths; ambiguous tokens are skipped.

    Requires a slash so dotted modules and bare prose words are ignored, rejects
    globs and absolute paths, and requires either a trailing slash (a directory)
    or a known file extension so prose like `try/except` is not treated as a path.
    """
    if "/" not in token or token.startswith("/"):
        return False
    if any(c in token for c in " (*"):
        return False
    return token.endswith("/") or token.rsplit(".", 1)[-1] in PATH_EXTENSIONS


def _private_method(token: str) -> str | None:
    """Extract a leading-underscore method name from a citation, else None.

    Handles bare (`_reconcile`), called (`_reconcile()`), and qualified
    (`GarmConfiguratorCharm._reconcile`) forms.
    """
    name = token.split("(", 1)[0].rsplit(".", 1)[-1]
    return name if PRIVATE_METHOD.match(name) else None


def _defines_method(roots: list[Path], method: str) -> bool:
    """True if any first-party Python file under a root defines the method."""
    # Anchor on the name followed by "(" so `def _reconcile_state` does not
    # satisfy a citation for `_reconcile`.
    pattern = re.compile(rf"def {re.escape(method)}\s*\(")
    for root in roots:
        for py in root.rglob("*.py"):
            if _excluded(py):
                continue
            if pattern.search(py.read_text(encoding="utf-8")):
                return True
    return False


def _collect_tox_envs() -> set[str]:
    """Gather valid tox env names from env_list and [testenv:NAME] headers."""
    envs: set[str] = set()
    tox_ini = REPO_ROOT / "tox.ini"
    if not tox_ini.exists():
        return envs
    for line in tox_ini.read_text(encoding="utf-8").splitlines():
        header = re.match(r"\[testenv:([\w-]+)\]", line.strip())
        if header:
            envs.add(header.group(1))
        elif line.strip().startswith("env_list"):
            envs.update(e.strip() for e in line.split("=", 1)[1].split(","))
    return envs


def _excluded(path: Path) -> bool:
    """True if the path lives in a vendored, generated, build, or test directory."""
    return any(part in EXCLUDE_DIRS for part in path.parts)


if __name__ == "__main__":
    sys.exit(main())
