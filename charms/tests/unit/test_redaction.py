# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Unit tests for the diagnostic redaction helpers in ``tests.integration.conftest``.

A redactor that stops matching fails silently -- the suites go green and the
credential lands in the log -- so it is checked here rather than only in the
live-model runs that depend on it.
"""

import base64

import yaml

from tests.integration.conftest import _credential_sentinels, _redact_pebble_output


def test_redact_pebble_output_removes_environment():
    """
    arrange: A sample Pebble plan YAML containing an environment block.
    act: Run _redact_pebble_output on the YAML string.
    assert: The environment entry is replaced with [REDACTED].
    """
    sample_plan = yaml.safe_dump({
        "services": {
            "garm": {
                "override": "replace",
                "command": "/charm/bin/garm",
                "environment": {
                    "GARM_PROVIDERS_JSON": '[{"password": "secret-openstack-password"}]',
                    "SOME_OTHER_KEY": "some-value",
                },
            }
        }
    })

    redacted = _redact_pebble_output(sample_plan)
    assert "secret-openstack-password" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_pebble_output_with_sentinel_values():
    """
    arrange: A sample output containing cleartext sentinel passwords in arbitrary text.
    act: Run _redact_pebble_output with sentinel_values specified.
    assert: All occurrences of the sentinel passwords are replaced with [REDACTED].
    """
    sample_output = "Connected with password secret-tenant-pass123 in log line."
    redacted = _redact_pebble_output(
        sample_output, sentinel_values=["secret-tenant-pass123"]
    )
    assert "secret-tenant-pass123" not in redacted
    assert "[REDACTED]" in redacted


def test_credential_sentinels_reads_env(monkeypatch):
    """
    arrange: OS_USERNAME, OS_PASSWORD and a base64-encoded TEST_GITHUB_APP_PRIVATE_KEY
        set in the environment.
    act: Call _credential_sentinels.
    assert: The username, the raw password, the base64 form, and its decoded PEM form
        are all returned, so the username is redacted like the password it travels with.
    """
    pem_body = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
    encoded_key = base64.b64encode(pem_body.encode()).decode()
    monkeypatch.setenv("OS_USERNAME", "tenant-bot")
    monkeypatch.setenv("OS_PASSWORD", "super-secret-pw")
    monkeypatch.setenv("TEST_GITHUB_APP_PRIVATE_KEY", encoded_key)

    sentinels = _credential_sentinels()

    assert "tenant-bot" in sentinels
    assert "super-secret-pw" in sentinels
    assert encoded_key in sentinels
    assert pem_body in sentinels


def test_credential_sentinels_excludes_unset_vars(monkeypatch):
    """
    arrange: None of OS_USERNAME, OS_PASSWORD nor TEST_GITHUB_APP_PRIVATE_KEY set in
        the environment.
    act: Call _credential_sentinels.
    assert: No sentinel values are returned, so unset credentials never masquerade as redaction targets.
    """
    monkeypatch.delenv("OS_USERNAME", raising=False)
    monkeypatch.delenv("OS_PASSWORD", raising=False)
    monkeypatch.delenv("TEST_GITHUB_APP_PRIVATE_KEY", raising=False)

    assert _credential_sentinels() == []
