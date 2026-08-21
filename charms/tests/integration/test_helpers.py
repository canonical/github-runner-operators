# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the shared integration helpers."""

import base64

import pytest

from tests.integration.helpers import (
    INTEGRATION_APP_ENV,
    TEST_RSA_PRIVATE_KEY,
    github_app_private_key,
)


@pytest.mark.parametrize(
    "stored",
    [
        pytest.param(TEST_RSA_PRIVATE_KEY, id="pem-as-issued"),
        pytest.param(
            base64.b64encode(TEST_RSA_PRIVATE_KEY.encode()).decode(), id="base64-encoded"
        ),
    ],
)
def test_github_app_private_key_accepts_either_form(monkeypatch, stored: str):
    """
    arrange: The private key set in the environment, once as the PEM GitHub issues and
        once base64-encoded as CI carries it.
    act: Read it back through github_app_private_key.
    assert: Both yield the same PEM, so a key pasted directly and a key encoded for
        transport authenticate identically.
    """
    monkeypatch.setenv(INTEGRATION_APP_ENV.private_key, stored)

    assert github_app_private_key(INTEGRATION_APP_ENV) == TEST_RSA_PRIVATE_KEY


def test_github_app_private_key_rejects_a_mangled_value(monkeypatch):
    """
    arrange: A private key that is neither a PEM nor valid base64.
    act: Read it back through github_app_private_key.
    assert: It fails naming the variable, rather than decoding to plausible bytes that
        would surface later as an opaque authentication error.
    """
    monkeypatch.setenv(INTEGRATION_APP_ENV.private_key, "not a key!!")

    with pytest.raises(pytest.fail.Exception, match=INTEGRATION_APP_ENV.private_key):
        github_app_private_key(INTEGRATION_APP_ENV)
