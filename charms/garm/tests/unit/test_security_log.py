# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the security_log singleton."""

import json
import logging
from datetime import datetime

import pytest

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


def test_timestamp_is_utc_rendered(caplog):
    """
    arrange: Capture logs at INFO on the owasp-logger logger.
    act: Emit a security event.
    assert: The datetime is RFC3339 UTC ('Z'-suffixed), so entries are UTC-aligned
        regardless of the host timezone.
    """
    with caplog.at_level(logging.INFO):
        owasp_log.authn_login_success(userid="admin", description="test")
    record = json.loads(caplog.records[-1].getMessage())["owasp_event"]
    assert record["datetime"].endswith("Z")
    datetime.fromisoformat(record["datetime"].replace("Z", "+00:00"))


def test_configure_otlp_forwarding_noop_on_empty_endpoint():
    """
    arrange: The dedicated security logger with no OTLP handler attached.
    act: Call configure_otlp_forwarding with an empty endpoint.
    assert: No handler is attached, so an unrelated charm (no configurator endpoint) does not
        start an exporter.
    """
    from opentelemetry.sdk._logs import LoggingHandler

    from security_log import _SECURITY_LOGGER, configure_otlp_forwarding

    before = [h for h in _SECURITY_LOGGER.handlers if isinstance(h, LoggingHandler)]
    configure_otlp_forwarding("")
    after = [h for h in _SECURITY_LOGGER.handlers if isinstance(h, LoggingHandler)]
    assert before == after


def test_configure_otlp_forwarding_attaches_handler_once():
    """
    arrange: The dedicated security logger.
    act: Call configure_otlp_forwarding twice with an endpoint.
    assert: Exactly one OTLP LoggingHandler is attached, so charm-hook security events are
        exported without duplicating handlers across hooks.
    """
    from opentelemetry.sdk._logs import LoggingHandler

    from security_log import _SECURITY_LOGGER, configure_otlp_forwarding

    added = []
    try:
        configure_otlp_forwarding("localhost:4317")
        configure_otlp_forwarding("localhost:4317")
        added = [h for h in _SECURITY_LOGGER.handlers if isinstance(h, LoggingHandler)]
        assert len(added) == 1
    finally:
        for handler in added:
            _SECURITY_LOGGER.removeHandler(handler)


@pytest.mark.parametrize(
    "endpoint, expected_target, expected_insecure",
    [
        ("https://collector:4317", "collector:4317", False),
        ("http://collector:4317", "collector:4317", True),
        ("collector:4317", "collector:4317", True),
    ],
    ids=["https-uses-tls", "http-is-plaintext", "bare-host-is-plaintext"],
)
def test_otlp_target_and_security_derives_tls_from_scheme(
    endpoint, expected_target, expected_insecure
):
    """
    arrange: An endpoint as advertised by the garm-configurator relation.
    act: Resolve it to a gRPC target and TLS mode.
    assert: The scheme is stripped to a host:port target and TLS is used only for https, so an
        https collector is not forced onto a plaintext channel and silently dropped.
    """
    from security_log import _otlp_target_and_security

    assert _otlp_target_and_security(endpoint) == (expected_target, expected_insecure)
