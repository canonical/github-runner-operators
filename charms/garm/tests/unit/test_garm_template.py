# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for garm_template."""

import base64
from unittest.mock import MagicMock, call

import pytest

import garm_template
from charm_state import SSHDebugInfo
from garm_api import GarmApiError

_CONN = SSHDebugInfo(host="h", port=10022, rsa_fingerprint="rsa-fp", ed25519_fingerprint="ed-fp")


# ---------------------------------------------------------------------------
# apply_charmed_template
# ---------------------------------------------------------------------------


def test_apply_charmed_template_deletes_when_no_connections_and_charmed_exists():
    """
    arrange: list_templates returns a charmed template; no debug-ssh connections.
    act: Call apply_charmed_template() with an empty connections list.
    assert: delete_template is called; no create/update.
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.name = garm_template.GARM_CHARMED_TEMPLATE_NAME
    charmed.id = 5
    client.list_templates.return_value = [charmed]

    garm_template.apply_charmed_template(client, [])

    client.delete_template.assert_called_once_with(charmed.id)
    client.create_template.assert_not_called()
    client.update_template.assert_not_called()


def test_apply_charmed_template_no_op_when_no_connections_and_no_charmed():
    """
    arrange: list_templates returns no charmed template; no connections.
    act: Call apply_charmed_template() with an empty connections list.
    assert: No delete/create/update calls are made.
    """
    client = MagicMock()
    client.list_templates.return_value = []

    garm_template.apply_charmed_template(client, [])

    client.delete_template.assert_not_called()
    client.create_template.assert_not_called()
    client.update_template.assert_not_called()


def test_apply_charmed_template_raises_when_base_template_missing():
    """
    arrange: list_templates returns no base template; connections present.
    act: Call apply_charmed_template().
    assert: CharmedTemplateError is raised.
    """
    client = MagicMock()
    client.list_templates.return_value = []

    with pytest.raises(
        garm_template.CharmedTemplateError, match=garm_template.GARM_BASE_TEMPLATE_NAME
    ):
        garm_template.apply_charmed_template(client, [_CONN])


def test_apply_charmed_template_syncs_when_connections_and_base_exists():
    """
    arrange: list_templates returns base + charmed; connections present; data differs.
    act: Call apply_charmed_template().
    assert: update_template is called (sync path).
    """
    client = MagicMock()
    base = MagicMock()
    base.name = garm_template.GARM_BASE_TEMPLATE_NAME
    base.id = 1
    charmed = MagicMock()
    charmed.name = garm_template.GARM_CHARMED_TEMPLATE_NAME
    charmed.id = 2
    client.list_templates.return_value = [base, charmed]

    # base script with shebang so prepend_after_shebang works
    base_template = MagicMock()
    base_template.data = base64.b64encode(b"#!/bin/bash\necho hi\n").decode()
    client.get_template.side_effect = [
        base_template,  # _build_charmed_template_data fetch
        MagicMock(data=None),  # _sync_charmed_template change-check (data=None → proceed)
    ]

    garm_template.apply_charmed_template(client, [_CONN])

    client.update_template.assert_called_once()


def test_apply_charmed_template_propagates_garm_api_error_from_list_templates():
    """
    arrange: list_templates raises GarmApiError.
    act: Call apply_charmed_template().
    assert: GarmApiError propagates to the caller.
    """
    client = MagicMock()
    client.list_templates.side_effect = GarmApiError("boom")

    with pytest.raises(GarmApiError):
        garm_template.apply_charmed_template(client, [_CONN])


# ---------------------------------------------------------------------------
# _delete_charmed_template_if_present
# ---------------------------------------------------------------------------


def test_delete_charmed_template_if_present_no_op_when_charmed_is_none():
    """
    arrange: charmed is None (template does not exist).
    act: Call _delete_charmed_template_if_present().
    assert: delete_template is not called.
    """
    client = MagicMock()
    garm_template._delete_charmed_template_if_present(client, None)
    client.delete_template.assert_not_called()


def test_delete_charmed_template_if_present_calls_delete_when_charmed_exists():
    """
    arrange: charmed template exists.
    act: Call _delete_charmed_template_if_present().
    assert: delete_template is called with the correct id.
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.id = 99

    garm_template._delete_charmed_template_if_present(client, charmed)

    client.delete_template.assert_called_once_with(99)


def test_delete_charmed_template_if_present_raises_on_api_error():
    """
    arrange: delete_template raises GarmApiError.
    act: Call _delete_charmed_template_if_present().
    assert: CharmedTemplateError is raised.
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.id = 3
    client.delete_template.side_effect = GarmApiError("network error")

    with pytest.raises(garm_template.CharmedTemplateError):
        garm_template._delete_charmed_template_if_present(client, charmed)


# ---------------------------------------------------------------------------
# _build_charmed_template_data
# ---------------------------------------------------------------------------


def test_build_charmed_template_data_raises_on_api_error():
    """
    arrange: get_template raises GarmApiError.
    act: Call _build_charmed_template_data().
    assert: CharmedTemplateError is raised.
    """
    client = MagicMock()
    client.get_template.side_effect = GarmApiError("timeout")

    with pytest.raises(garm_template.CharmedTemplateError):
        garm_template._build_charmed_template_data(client, 1, [_CONN])


def test_build_charmed_template_data_raises_when_data_is_null():
    """
    arrange: get_template returns a Template whose .data is None.
    act: Call _build_charmed_template_data().
    assert: CharmedTemplateError is raised.
    """
    client = MagicMock()
    template = MagicMock()
    template.data = None
    client.get_template.return_value = template

    with pytest.raises(
        garm_template.CharmedTemplateError, match=garm_template.GARM_BASE_TEMPLATE_NAME
    ):
        garm_template._build_charmed_template_data(client, 1, [_CONN])


def test_build_charmed_template_data_prepends_snippet_after_shebang():
    """
    arrange: get_template returns a base script with a shebang.
    act: Call _build_charmed_template_data().
    assert: Returned bytes start with the shebang; tmate env vars are present.
    """
    client = MagicMock()
    base_script = "#!/bin/bash\necho hello\n"
    template = MagicMock()
    template.data = base64.b64encode(base_script.encode()).decode()
    client.get_template.return_value = template

    result = garm_template._build_charmed_template_data(client, 1, [_CONN])

    decoded = result.decode()
    assert decoded.startswith("#!/bin/bash\n")
    assert f"TMATE_SERVER_HOST={_CONN.host}" in decoded
    assert f"TMATE_SERVER_PORT={_CONN.port}" in decoded
    assert f"TMATE_SERVER_RSA_FINGERPRINT={_CONN.rsa_fingerprint}" in decoded
    assert f"TMATE_SERVER_ED25519_FINGERPRINT={_CONN.ed25519_fingerprint}" in decoded
    assert "echo hello" in decoded


# ---------------------------------------------------------------------------
# _sync_charmed_template
# ---------------------------------------------------------------------------


def test_sync_charmed_template_updates_when_data_changed():
    """
    arrange: Charmed template exists; patched_data differs from current body.
    act: Call _sync_charmed_template().
    assert: update_template is called; create_template is NOT called.
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.id = 42
    current = MagicMock()
    current.data = base64.b64encode(b"old-data").decode()
    client.get_template.return_value = current

    garm_template._sync_charmed_template(client, charmed, b"new-data", 1)

    client.update_template.assert_called_once_with(42, b"new-data")
    client.create_template.assert_not_called()


def test_sync_charmed_template_skips_when_data_unchanged():
    """
    arrange: Charmed template exists; body matches patched_data exactly.
    act: Call _sync_charmed_template().
    assert: Neither update_template nor create_template is called.
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.id = 7
    data = b"same-data"
    current = MagicMock()
    current.data = base64.b64encode(data).decode()
    client.get_template.return_value = current

    garm_template._sync_charmed_template(client, charmed, data, 1)

    client.update_template.assert_not_called()
    client.create_template.assert_not_called()


def test_sync_charmed_template_updates_when_get_raises():
    """
    arrange: get_template raises GarmApiError (can't verify current state).
    act: Call _sync_charmed_template().
    assert: update_template is called anyway (safe to overwrite).
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.id = 11
    client.get_template.side_effect = GarmApiError("unreachable")

    garm_template._sync_charmed_template(client, charmed, b"data", 1)

    client.update_template.assert_called_once_with(11, b"data")


def test_sync_charmed_template_raises_when_update_fails():
    """
    arrange: Charmed template exists; update_template raises GarmApiError.
    act: Call _sync_charmed_template().
    assert: CharmedTemplateError is raised.
    """
    client = MagicMock()
    charmed = MagicMock()
    charmed.id = 13
    client.get_template.return_value = MagicMock(data=None)
    client.update_template.side_effect = GarmApiError("write error")

    with pytest.raises(garm_template.CharmedTemplateError):
        garm_template._sync_charmed_template(client, charmed, b"data", 1)


def test_sync_charmed_template_creates_when_charmed_absent():
    """
    arrange: No existing charmed template (charmed=None).
    act: Call _sync_charmed_template().
    assert: create_template is called; update_template is NOT called.
    """
    client = MagicMock()

    garm_template._sync_charmed_template(client, None, b"script", 1)

    client.create_template.assert_called_once()
    client.update_template.assert_not_called()


def test_sync_charmed_template_raises_when_create_fails():
    """
    arrange: No existing charmed template; create_template raises GarmApiError.
    act: Call _sync_charmed_template().
    assert: CharmedTemplateError is raised.
    """
    client = MagicMock()
    client.create_template.side_effect = GarmApiError("quota exceeded")

    with pytest.raises(garm_template.CharmedTemplateError):
        garm_template._sync_charmed_template(client, None, b"script", 1)
