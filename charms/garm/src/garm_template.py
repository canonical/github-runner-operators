# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed runner install template management for GARM."""

import base64
import logging
import typing

from charm_state import SSHDebugInfo
from garm_api import GarmApiError, GarmAuthenticatedClient
from runner_paths import RUNNER_ENV_PATH, RUNNER_USER, prepend_after_shebang

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


def build_env_snippet(connections: list[SSHDebugInfo]) -> str:
    """Render the writer for the runner's ``.env`` file.

    The GitHub Actions runner applies ``.env`` to its own environment before any
    job starts, so steps inherit these values.

    The first two entries are the account the runner UID resolves to, because
    the runner images create ``runner`` as a duplicate-UID alias of ``ubuntu``:
    every lookup keyed on the UID — ``getpwuid``, and with it ``sg``, ``newgrp``,
    ``chown`` and sbuild's schroot user — resolves to ``ubuntu``, so a step that
    read ``$USER`` acted on a different account than those tools check. Resolving
    on the instance keeps the snippet correct if the account layout changes: it
    yields ``ubuntu`` on the current images and ``runner`` on an image that gives
    the account its own UID, where the override is a no-op.

    The tmate variables are appended only when debug-ssh connections exist and
    use a quoted heredoc, so relation-provided values are written verbatim.

    Args:
        connections: Debug-ssh connections; empty means no tmate variables.

    Returns:
        A shell snippet string (no shebang) writing the entries to ``.env``.
    """
    # TODO(#438): drop the USER/LOGNAME entries once the runner account layout is
    # settled; the alias, and with it this override, should disappear.
    lines = [
        f"mkdir -p $(dirname {RUNNER_ENV_PATH})",
        # `id -u` works whoever runs the template (cloud-init runs it as root).
        f'runner_account="$(getent passwd "$(id -u {RUNNER_USER})" | cut -d: -f1)"',
        # printf rather than a heredoc: the value must expand on the instance,
        # while the guard avoids blanking USER when the lookup fails.
        f"[ -n \"$runner_account\" ] && printf 'USER=%s\\nLOGNAME=%s\\n' "
        f'"$runner_account" "$runner_account" >> {RUNNER_ENV_PATH}',
    ]
    if connections:
        conn = connections[0]
        # Global env write: injected into the shared github_linux_charmed
        # template, so these apply to every scaleset (a separate .env append
        # from the per-scaleset one in runner_template.render_pre_job_hooks).
        lines += [
            f'cat >> {RUNNER_ENV_PATH} << "EOF"',
            f"TMATE_SERVER_HOST={conn.host}",
            f"TMATE_SERVER_PORT={conn.port}",
            f"TMATE_SERVER_RSA_FINGERPRINT={conn.rsa_fingerprint}",
            f"TMATE_SERVER_ED25519_FINGERPRINT={conn.ed25519_fingerprint}",
            "EOF",
        ]
    lines.append("")
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
    snippet = build_env_snippet(connections)
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
