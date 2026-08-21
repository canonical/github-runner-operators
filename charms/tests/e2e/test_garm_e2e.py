# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""GARM end-to-end test.

TODO: This module is deliberately incomplete. It exists so that the workflows have
something to run; the end-to-end implementation lands in a follow-up. What is here
asserts only that the credentials reach pytest.

Still to come: deploy postgresql, GARM, a traefik ingress and garm-configurator; assert
the GARM API is reachable and the provider authenticates to OpenStack; assert a VM is
created from the runner image and the runner registers with GitHub; then dispatch
``garm_e2e_test_run.yaml`` at the scale set's label and assert the job is picked up and
exits clean.
"""

import os

import pytest

# Settings the deployment fixtures will need. The OpenStack username and password come
# from Vault, the rest from repository secrets; both routes converge on the job
# environment, which tox forwards to pytest.
REQUIRED_SETTINGS = (
    "OS_AUTH_URL",
    "OS_USERNAME",
    "OS_PASSWORD",
    "OS_PROJECT_NAME",
    "OS_USER_DOMAIN_NAME",
    "OS_PROJECT_DOMAIN_NAME",
    "OS_REGION_NAME",
    "OS_NETWORK",
    "E2E_GITHUB_APP_ID",
    "E2E_GITHUB_APP_INSTALLATION_ID",
    "E2E_GITHUB_APP_PRIVATE_KEY",
)


@pytest.mark.parametrize("setting", REQUIRED_SETTINGS)
def test_setting_reaches_pytest(setting: str):
    """
    arrange: The workflow has resolved the settings, taking the OpenStack username and
        password from Vault and the rest from repository secrets, and exported them.
    act: Read the setting pytest inherited through tox.
    assert: It is present, so the deployment fixtures can authenticate to the tenant and
        to GitHub.
        Only the name is reported on failure — printing the value would defeat the
        masking the workflow applied.
    """
    # pytest.fail rather than assert: assertion rewriting would introspect the
    # expression and dump the whole of os.environ into the failure output.
    if not os.environ.get(setting):
        pytest.fail(
            f"{setting} did not reach pytest. Check that the workflow exports it and "
            f"that tox passes it through in the garm-e2e environment."
        )
