# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""GARM end-to-end test — one test for the full chain.

Arrange:
    GARM deployed with postgresql + traefik ingress; garm-configurator holding real
    ProdStack credentials, a stable runner-image name, and a unique run label;
    GARM's controller metadata_url resolved to the routable LB address.

Act:
    Dispatch ``garm_e2e_test_run.yaml`` against the run label and wait for completion.

Assert:
    The workflow run concludes ``"success"`` — which is only reachable if GARM
    authenticated to OpenStack, booted a VM on the published image, the runner
    registered with GitHub, picked up the job, and exited clean.
"""

import logging
import os

import pytest

from tests.integration.helpers import (
    create_github_app_client,
    dispatch_workflow,
    required_env,
    wait_for_completion,
)

logger = logging.getLogger(__name__)

WORKFLOW_PATH = ".github/workflows/garm_e2e_test_run.yaml"


@pytest.mark.skipif(
    not os.environ.get("GITHUB_RUN_ID"),
    reason="Only runs inside a GitHub Actions workflow",
)
@pytest.mark.skipif(
    not os.environ.get("E2E_RUNNER_IMAGE_NAME"),
    reason="E2E_RUNNER_IMAGE_NAME not set — runner image unknown",
)
def test_garm_e2e(e2e_scaleset: str):
    """Run the full GARM E2E chain on ProdStack."""
    repo_path = required_env("TEST_GITHUB_PATH")
    label = e2e_scaleset  # garm-configurator app name is the run label
    ref = os.environ.get("GITHUB_REF_NAME", "main")

    github_client = create_github_app_client()

    logger.info("Dispatching %s on %s with label %s", WORKFLOW_PATH, ref, label)
    run_id = dispatch_workflow(
        github_client=github_client,
        repo_path=repo_path,
        workflow_path=WORKFLOW_PATH,
        ref=ref,
        inputs={"runner-label": label},
    )

    logger.info("Workflow run %d dispatched, waiting for completion", run_id)
    conclusion = wait_for_completion(
        github_client=github_client,
        repo_path=repo_path,
        run_id=run_id,
        poll_interval=15,
        timeout=600,
    )

    assert conclusion == "success", (
        f"Workflow run {run_id} concluded as '{conclusion}', expected 'success'"
    )
    logger.info("GARM E2E test passed: workflow run %s concluded as 'success'", run_id)
