# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the security_log singleton."""

import json
import logging

from security_log import APPID, owasp_log


def test_singleton_appid():
    """
    arrange: The module-level owasp_log singleton.
    act: Read its configured appid.
    assert: appid is 'canonical.garm', the single source of truth shared with Sigma rules.
    """
    assert APPID == "canonical.garm"


def test_emits_owasp_envelope(caplog):
    """
    arrange: Capture logs at INFO on the owasp-logger logger.
    act: Emit an authn_login_success event.
    assert: A JSON security envelope is produced carrying appid, the event token, and level.
    """
    with caplog.at_level(logging.INFO):
        owasp_log.authn_login_success(userid="admin", description="test")
    record = json.loads(caplog.records[-1].getMessage())["owasp_event"]
    assert record["appid"] == "canonical.garm"
    assert record["type"] == "security"
    assert record["event"] == "authn_login_success:admin"
    assert record["level"] == "INFO"
