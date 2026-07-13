# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared runner-install paths and template-splicing primitives.

Both template-injection flows — the global ``github_linux_charmed`` template
(:mod:`garm_template`) and the per-scaleset templates (:mod:`runner_template`) —
prepend shell after the shebang and append to the same runner ``.env`` file.
Keeping the paths and the splice helper here gives them one source of truth so
the two flows cannot drift apart.
"""

# GARM installs the runner under the `runner` user's home; the GitHub Actions
# runner sources a `.env` dotfile from that install directory.
RUNNER_USER = "runner"
RUNNER_HOME = "/home/runner/actions-runner"
PRE_JOB_HOOK_PATH = f"{RUNNER_HOME}/pre-job.sh"
RUNNER_ENV_PATH = f"{RUNNER_HOME}/.env"


def prepend_after_shebang(script: str, snippet: str) -> str:
    """Insert *snippet* immediately after the shebang line of *script*.

    The runner install scripts these flows patch always start with a ``#!``
    shebang, so the snippet lands on its own line right after it. If no shebang
    is present the snippet is prepended at the very start instead. Either way the
    snippet is separated from the following body by a newline, so a snippet that
    is not newline-terminated cannot run into the next line.

    Args:
        script: The original shell script (may start with ``#!``).
        snippet: The shell code to inject.

    Returns:
        The modified script string. An empty *snippet* leaves *script* unchanged.
    """
    if not snippet:
        return script
    body = snippet if snippet.endswith("\n") else snippet + "\n"
    if script.startswith("#!"):
        shebang, _, rest = script.partition("\n")
        return f"{shebang}\n{body}{rest}"
    return f"{body}{script}"
