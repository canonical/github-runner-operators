# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed runner install template management for GARM."""

import base64
import logging
import typing

from charm_state import SSHDebugInfo
from garm_api import GarmApiClient, GarmApiError, build_tmate_env_snippet, prepend_after_shebang

logger = logging.getLogger(__name__)

GARM_BASE_TEMPLATE_NAME: typing.Final[str] = "github_linux"
GARM_CHARMED_TEMPLATE_NAME: typing.Final[str] = "github_linux_charmed"


class CharmedTemplateError(Exception):
    """Raised when charmed template management fails; message is used as the unit status."""


def apply_charmed_template(
    client: GarmApiClient,
    token: str,
    connections: list[SSHDebugInfo],
) -> None:
    """Create, update, or delete the charmed runner install template in GARM.

    Derives ``github_linux_charmed`` from the built-in ``github_linux`` base
    by prepending a shell snippet that writes tmate environment variables to
    the runner's ``.env`` file.

    Args:
        client: Authenticated GARM API client.
        token: JWT token from a prior login call.
        connections: Current debug-ssh connections; empty list triggers deletion.

    Raises:
        CharmedTemplateError: If any template operation fails.
        GarmApiError: If the GARM API call to list templates fails.
    """
    templates = client.list_templates(token)
    charmed = next((t for t in templates if t.name == GARM_CHARMED_TEMPLATE_NAME), None)

    if not connections:
        _delete_charmed_template_if_present(client, token, charmed)
        return

    base = next((t for t in templates if t.name == GARM_BASE_TEMPLATE_NAME), None)
    if base is None:
        raise CharmedTemplateError(f"Base template '{GARM_BASE_TEMPLATE_NAME}' not found in GARM")
    if base.id is None:
        raise CharmedTemplateError(f"Base template '{GARM_BASE_TEMPLATE_NAME}' has no ID")

    patched_data = _build_charmed_template_data(client, token, base.id, connections)
    _sync_charmed_template(client, token, charmed, patched_data, len(connections))


def _delete_charmed_template_if_present(
    client: GarmApiClient,
    token: str,
    charmed: typing.Any,
) -> None:
    """Delete the charmed template when no debug-ssh connections remain."""
    if charmed is None:
        return
    logger.info("No debug-ssh connections; deleting charmed template (id=%s)", charmed.id)
    try:
        client.delete_template(token, charmed.id)
    except GarmApiError as exc:
        raise CharmedTemplateError(f"Failed to delete charmed template (id={charmed.id})") from exc


def _build_charmed_template_data(
    client: GarmApiClient,
    token: str,
    base_id: int,
    connections: list[SSHDebugInfo],
) -> bytes:
    """Fetch the base template and build the patched script bytes.

    Args:
        client: Authenticated GARM API client.
        token: JWT token.
        base_id: ID of the base template to fetch.
        connections: Debug-ssh connections used to build the tmate snippet.

    Returns:
        Patched shell script as bytes.

    Raises:
        CharmedTemplateError: If the base template data cannot be fetched or is empty.
    """
    try:
        base_template = client.get_template(token, base_id)
    except GarmApiError as exc:
        raise CharmedTemplateError("Failed to fetch base template data") from exc

    if base_template.data is None:
        raise CharmedTemplateError(f"Base template '{GARM_BASE_TEMPLATE_NAME}' has no body")

    # GARM returns the template body as a base64-encoded string.
    base_script = base64.b64decode(base_template.data).decode("utf-8")
    snippet = build_tmate_env_snippet(connections)
    return prepend_after_shebang(base_script, snippet).encode("utf-8")


def _sync_charmed_template(
    client: GarmApiClient,
    token: str,
    charmed: typing.Any,
    patched_data: bytes,
    n_connections: int,
) -> None:
    """Create or atomically update the charmed template; skip if unchanged."""
    if charmed is not None:
        try:
            current = client.get_template(token, charmed.id)
            if current.data is not None and base64.b64decode(current.data) == patched_data:
                logger.debug("Charmed template unchanged; skipping update")
                return
        except GarmApiError:
            pass  # proceed to update

        logger.info(
            "Updating charmed template (id=%s) with %d tmate connection(s)",
            charmed.id,
            n_connections,
        )
        try:
            client.update_template(token, charmed.id, patched_data)
        except GarmApiError as exc:
            raise CharmedTemplateError(
                f"Failed to update charmed template (id={charmed.id})"
            ) from exc
        return

    logger.info(
        "Creating charmed template '%s' with %d tmate connection(s)",
        GARM_CHARMED_TEMPLATE_NAME,
        n_connections,
    )
    try:
        client.create_template(
            token=token,
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
