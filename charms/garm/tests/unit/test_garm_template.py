# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for garm_template."""

import base64
from unittest.mock import MagicMock

import pytest

import garm_template
from charm_state import SSHDebugInfo
from garm_api import GarmApiError

_CONN = SSHDebugInfo(host="h", port=10022, rsa_fingerprint="rsa-fp", ed25519_fingerprint="ed-fp")


def test_ssh_debug_info_env_vars():
    """
    arrange: One SSHDebugInfo connection.
    act: Call build_tmate_env_snippet() and prepend_after_shebang().
    assert: The patched script starts with the shebang, then contains
            all four TMATE_SERVER_* variables with correct values.
    """
    conn = SSHDebugInfo(
        host="10.10.0.5",
        port=2222,
        rsa_fingerprint="SHA256:rsa",
        ed25519_fingerprint="SHA256:ed",
    )
    base_script = "#!/bin/bash\necho 'hello'\n"

    snippet = garm_template.build_tmate_env_snippet([conn])
    patched = garm_template.prepend_after_shebang(base_script, snippet)

    assert patched.startswith("#!/bin/bash\n")
    assert "cat >> /home/runner/actions-runner/.env <<" in patched
    assert "TMATE_SERVER_HOST=10.10.0.5" in patched
    assert "TMATE_SERVER_PORT=2222" in patched
    assert "TMATE_SERVER_RSA_FINGERPRINT=SHA256:rsa" in patched
    assert "TMATE_SERVER_ED25519_FINGERPRINT=SHA256:ed" in patched
    assert "echo 'hello'" in patched


def test_prepend_after_shebang_no_shebang_prepends_at_start():
    """
    arrange: A script that does not start with a shebang and a snippet.
    act: Call prepend_after_shebang().
    assert: The snippet is prepended at the very start, on its own line, with the
            original script body preserved intact after it.
    """
    patched = garm_template.prepend_after_shebang("echo original\n", "echo injected\n")

    assert patched == "echo injected\necho original\n"


def test_prepend_after_shebang_separates_snippet_without_trailing_newline():
    """
    arrange: A shebang script and a snippet that is not newline-terminated.
    act: Call prepend_after_shebang().
    assert: The snippet does not run into the following body line — a newline is
            inserted so the injected code and the original body stay separate.
    """
    patched = garm_template.prepend_after_shebang("#!/bin/bash\necho body\n", "echo injected")

    assert patched == "#!/bin/bash\necho injected\necho body\n"


def test_prepend_after_shebang_no_shebang_unterminated_snippet():
    """
    arrange: A script with no shebang and a snippet that is not newline-terminated.
    act: Call prepend_after_shebang().
    assert: The snippet is prepended at the start, separated from the body by a
            newline so the two do not run together.
    """
    patched = garm_template.prepend_after_shebang("echo original", "echo injected")

    assert patched == "echo injected\necho original"


def test_prepend_after_shebang_empty_snippet_leaves_script_unchanged():
    """
    arrange: A script and an empty snippet.
    act: Call prepend_after_shebang().
    assert: The script is returned unchanged — no stray blank line is injected.
    """
    script = "#!/bin/bash\necho body\n"

    assert garm_template.prepend_after_shebang(script, "") == script


def test_apply_charmed_template_maintains_when_no_connections_and_charmed_exists():
    """
    arrange: list_templates returns base + charmed; no debug-ssh connections.
    act: Call apply_charmed_template() with an empty connections list.
    assert: charmed template id is returned; template is not deleted.
    """
    client = MagicMock()
    base = MagicMock()
    base.name = garm_template.GARM_BASE_TEMPLATE_NAME
    base.id = 1
    charmed = MagicMock()
    charmed.name = garm_template.GARM_CHARMED_TEMPLATE_NAME
    charmed.id = 5
    client.list_templates.return_value = [base, charmed]
    base_template = MagicMock()
    base_template.data = base64.b64encode(b"#!/bin/bash\necho hi\n").decode()
    client.get_template.side_effect = [base_template, MagicMock(data=None)]

    result = garm_template.apply_charmed_template(client, [])

    assert result == 5
    client.delete_template.assert_not_called()
    client.create_template.assert_not_called()


def test_apply_charmed_template_creates_when_no_connections_and_no_charmed():
    """
    arrange: list_templates returns only the base template; no connections.
    act: Call apply_charmed_template() with an empty connections list.
    assert: charmed template is created and its id returned.
    """
    client = MagicMock()
    base = MagicMock()
    base.name = garm_template.GARM_BASE_TEMPLATE_NAME
    base.id = 1
    client.list_templates.return_value = [base]
    base_template = MagicMock()
    base_template.data = base64.b64encode(b"#!/bin/bash\necho hi\n").decode()
    client.get_template.return_value = base_template
    client.create_template.return_value = MagicMock(id=7)

    result = garm_template.apply_charmed_template(client, [])

    assert result == 7
    client.delete_template.assert_not_called()
    client.create_template.assert_called_once()


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


_PATCHED = b"patched-data"


@pytest.mark.parametrize(
    "charmed_exists, current_data, get_side_effect, write_side_effect, expected",
    [
        pytest.param(
            True,
            base64.b64encode(b"different").decode(),
            None,
            None,
            "update",
            id="exists-data-changed-updates",
        ),
        pytest.param(
            True,
            base64.b64encode(_PATCHED).decode(),
            None,
            None,
            "skip",
            id="exists-data-unchanged-skips",
        ),
        pytest.param(
            True,
            None,
            GarmApiError("unreachable"),
            None,
            "update",
            id="exists-get-raises-updates-anyway",
        ),
        pytest.param(
            True,
            None,
            None,
            GarmApiError("write error"),
            "raise",
            id="exists-update-fails-raises",
        ),
        pytest.param(False, None, None, None, "create", id="absent-creates"),
        pytest.param(
            False,
            None,
            None,
            GarmApiError("quota exceeded"),
            "raise",
            id="absent-create-fails-raises",
        ),
    ],
)
def test_sync_charmed_template(
    charmed_exists, current_data, get_side_effect, write_side_effect, expected
):
    """
    arrange: A charmed template (present or absent) plus the parametrized GARM behaviour.
    act: Call _sync_charmed_template() with a fixed patched body.
    assert: The expected GARM write happens (update/create/skip) or CharmedTemplateError raised.
    """
    client = MagicMock()
    charmed = None
    if charmed_exists:
        charmed = MagicMock()
        charmed.id = 42
        if get_side_effect is not None:
            client.get_template.side_effect = get_side_effect
        else:
            client.get_template.return_value = MagicMock(data=current_data)
    if write_side_effect is not None:
        target = client.update_template if charmed_exists else client.create_template
        target.side_effect = write_side_effect

    if expected == "raise":
        with pytest.raises(garm_template.CharmedTemplateError):
            garm_template._sync_charmed_template(client, charmed, _PATCHED, 1)
        return

    result = garm_template._sync_charmed_template(client, charmed, _PATCHED, 1)

    if expected == "update":
        client.update_template.assert_called_once_with(42, _PATCHED)
        client.create_template.assert_not_called()
        assert result == 42
    elif expected == "skip":
        client.update_template.assert_not_called()
        client.create_template.assert_not_called()
        assert result == 42
    elif expected == "create":
        client.create_template.assert_called_once()
        client.update_template.assert_not_called()


def test_apply_charmed_template_raises_when_charmed_has_no_id():
    """
    arrange: list_templates returns the base plus a charmed template whose id is None.
    act: Call apply_charmed_template().
    assert: CharmedTemplateError is raised (symmetric with the base-id guard).
    """
    client = MagicMock()
    base = MagicMock()
    base.name = garm_template.GARM_BASE_TEMPLATE_NAME
    base.id = 1
    charmed = MagicMock()
    charmed.name = garm_template.GARM_CHARMED_TEMPLATE_NAME
    charmed.id = None
    client.list_templates.return_value = [base, charmed]

    with pytest.raises(
        garm_template.CharmedTemplateError, match=garm_template.GARM_CHARMED_TEMPLATE_NAME
    ):
        garm_template.apply_charmed_template(client, [])
