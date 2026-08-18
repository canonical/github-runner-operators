# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Unit test for pebble output and diagnostic redaction."""

import yaml

from tests.integration.conftest import _redact_pebble_output


def test_redact_pebble_output_removes_environment_and_providers():
    """
    arrange: A sample Pebble plan YAML containing environment and GARM_PROVIDERS_JSON with secrets.
    act: Run _redact_pebble_output on the YAML string.
    assert: The environment and GARM_PROVIDERS_JSON entries are redacted.
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
    redacted = _redact_pebble_output(sample_output, sentinel_values=["secret-tenant-pass123"])
    assert "secret-tenant-pass123" not in redacted
    assert "[REDACTED]" in redacted
