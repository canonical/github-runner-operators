# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed runner install template management for GARM."""

import base64
import logging
import typing

from charm_state import SSHDebugInfo
from garm_api import GarmApiError, GarmAuthenticatedClient
from runner_paths import RUNNER_ENV_PATH, RUNNER_UID_USER, prepend_after_shebang

logger = logging.getLogger(__name__)

GARM_BASE_TEMPLATE_NAME: typing.Final[str] = "github_linux"
GARM_CHARMED_TEMPLATE_NAME: typing.Final[str] = "github_linux_charmed"


class CharmedTemplateError(Exception):
    """Raised when charmed template management fails; message is used as the unit status."""


def apply_charmed_template(
    client: GarmAuthenticatedClient,
    connections: list[SSHDebugInfo],
) -> int:
    """Create or update the charmed runner install template and return its id.

    Derives ``github_linux_charmed`` from the built-in ``github_linux`` base by
    prepending shell snippets, so scalesets can reference it unconditionally.
    The user-env snippet (``USER``/``LOGNAME`` matching the account the runner
    UID resolves to) is always present; the debug-ssh snippet (tmate env vars) is
    added only when connections are present. Scale sets with runner options
    derive their own template from this one, so both snippets travel with them.

    Args:
        client: Authenticated GARM API client.
        connections: Current debug-ssh connections; empty means no tmate snippet.

    Returns:
        The id of the charmed template.

    Raises:
        CharmedTemplateError: If any template operation fails or base is missing.
        GarmApiError: If the GARM API call to list templates fails.
    """
    templates = client.list_templates()
    charmed = next((t for t in templates if t.name == GARM_CHARMED_TEMPLATE_NAME), None)
    if charmed is not None and charmed.id is None:
        raise CharmedTemplateError(f"Charmed template '{GARM_CHARMED_TEMPLATE_NAME}' has no ID")

    base = next((t for t in templates if t.name == GARM_BASE_TEMPLATE_NAME), None)
    if base is None:
        raise CharmedTemplateError(f"Base template '{GARM_BASE_TEMPLATE_NAME}' not found in GARM")
    if base.id is None:
        raise CharmedTemplateError(f"Base template '{GARM_BASE_TEMPLATE_NAME}' has no ID")

    patched_data = _build_charmed_template_data(client, base.id, connections)
    return _sync_charmed_template(client, charmed, patched_data, len(connections))


def build_runner_env_snippet() -> str:
    """Build a shell snippet that aligns ``$USER``/``$LOGNAME`` with the UID.

    GARM starts the runner as ``runner``, which the runner images create as a
    duplicate-UID alias of ``ubuntu``. Every lookup keyed on the UID —
    ``getpwuid``, and with it ``sg``, ``newgrp`` and sbuild's schroot user —
    resolves to ``ubuntu``, so a job that read ``$USER`` acted on a different
    account than the one those tools check. The runner applies ``.env`` to its
    own environment before any job starts, so steps inherit these values and
    ``$USER`` matches the passwd entry the UID resolves to.

    Returns:
        A shell snippet string (no shebang) writing the two variables to the
        runner ``.env`` file.
    """
    lines = [
        f"mkdir -p $(dirname {RUNNER_ENV_PATH})",
        f"touch {RUNNER_ENV_PATH}",
        # Idempotent on reused instances: drop any previous value before writing.
        f"sed -i '/^USER=/d;/^LOGNAME=/d' {RUNNER_ENV_PATH}",
        f'cat >> {RUNNER_ENV_PATH} << "EOF"',
        f"USER={RUNNER_UID_USER}",
        f"LOGNAME={RUNNER_UID_USER}",
        "EOF",
        "",
    ]
    return "\n".join(lines)


def build_tmate_env_snippet(connections: list[SSHDebugInfo]) -> str:
    """Build a shell snippet that writes tmate env vars to the runner's .env file.

    Uses only the first connection (caller must sort for stability).

    Args:
        connections: List of SSHDebugInfo from the debug-ssh relation.

    Returns:
        A shell snippet string (no shebang) to be prepended to the base template,
        or an empty string when there are no connections.
    """
    if not connections:
        return ""
    conn = connections[0]
    # Global env write: injected into the shared github_linux_charmed template, so
    # these tmate vars apply to every scaleset (a separate .env append from the
    # per-scaleset one in runner_template.render_pre_job_hooks).
    runner_env = RUNNER_ENV_PATH
    lines = [
        f"mkdir -p $(dirname {runner_env})",
        f'cat >> {runner_env} << "EOF"',
        f"TMATE_SERVER_HOST={conn.host}",
        f"TMATE_SERVER_PORT={conn.port}",
        f"TMATE_SERVER_RSA_FINGERPRINT={conn.rsa_fingerprint}",
        f"TMATE_SERVER_ED25519_FINGERPRINT={conn.ed25519_fingerprint}",
        "EOF",
        "",
    ]
    return "\n".join(lines)


def _build_charmed_template_data(
    client: GarmAuthenticatedClient,
    base_id: int,
    connections: list[SSHDebugInfo],
) -> bytes:
    """Fetch the base template and build the patched script bytes.

    Args:
        client: Authenticated GARM API client.
        base_id: ID of the base template to fetch.
        connections: Debug-ssh connections used to build the tmate snippet; may
            be empty.

    Returns:
        Patched shell script as bytes.

    Raises:
        CharmedTemplateError: If the base template data cannot be fetched or is empty.
    """
    try:
        base_template = client.get_template(base_id)
    except GarmApiError as exc:
        raise CharmedTemplateError("Failed to fetch base template data") from exc

    if base_template.data is None:
        raise CharmedTemplateError(f"Base template '{GARM_BASE_TEMPLATE_NAME}' has no body")

    # GARM returns the template body as a base64-encoded string.
    base_script = base64.b64decode(base_template.data).decode("utf-8")
    snippet = build_runner_env_snippet() + build_tmate_env_snippet(connections)
    return prepend_after_shebang(base_script, snippet).encode("utf-8")


def _sync_charmed_template(
    client: GarmAuthenticatedClient,
    charmed: typing.Any,
    patched_data: bytes,
    n_connections: int,
) -> int:
    """Create or atomically update the charmed template; return its id."""
    if charmed is not None:
        return _update_charmed_template(client, charmed, patched_data, n_connections)
    return _create_charmed_template(client, patched_data, n_connections)


def _update_charmed_template(
    client: GarmAuthenticatedClient,
    charmed: typing.Any,
    patched_data: bytes,
    n_connections: int,
) -> int:
    """Update the charmed template in place if its data changed; return its id."""
    try:
        current = client.get_template(charmed.id)
        if current.data is not None and base64.b64decode(current.data) == patched_data:
            logger.debug("Charmed template unchanged; skipping update")
            return charmed.id
    except GarmApiError:
        pass  # proceed to update

    logger.info(
        "Updating charmed template (id=%s) with %d tmate connection(s)",
        charmed.id,
        n_connections,
    )
    try:
        client.update_template(charmed.id, patched_data)
    except GarmApiError as exc:
        raise CharmedTemplateError(f"Failed to update charmed template (id={charmed.id})") from exc
    return charmed.id


def _create_charmed_template(
    client: GarmAuthenticatedClient,
    patched_data: bytes,
    n_connections: int,
) -> int:
    """Create the charmed template; return its id."""
    logger.info(
        "Creating charmed template '%s' with %d tmate connection(s)",
        GARM_CHARMED_TEMPLATE_NAME,
        n_connections,
    )
    try:
        created = client.create_template(
            name=GARM_CHARMED_TEMPLATE_NAME,
            description="Charmed GitHub Linux template managed by the GARM charm",
            forge_type="github",
            os_type="linux",
            data=patched_data,
        )
    except GarmApiError as exc:
        raise CharmedTemplateError(
            f"Failed to create charmed template '{GARM_CHARMED_TEMPLATE_NAME}'"
        ) from exc
    if created.id is None:
        raise CharmedTemplateError(
            f"Created charmed template '{GARM_CHARMED_TEMPLATE_NAME}' has no ID"
        )
    return created.id
