# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the dispatch and credential helpers in ``tests.integration.helpers``.

Model-free by design, so they run as a merge gate rather than riding along on the
live-model suites that use these helpers.
"""

import base64
import time
from typing import Any

import pytest
from github import GithubException

from tests.integration.helpers import (
    INTEGRATION_APP_ENV,
    TEST_RSA_PRIVATE_KEY,
    dispatch_workflow,
    github_app_private_key,
    wait_for_completion,
)


class _FakeRun:
    """Stands in for a PyGithub workflow run: only id, status and conclusion are read."""

    def __init__(self, run_id: int, status: str = "queued", conclusion: str | None = None):
        self.id = run_id
        self.status = status
        self.conclusion = conclusion


class _FakeWorkflow:
    """Stands in for a PyGithub workflow: a dispatch makes a new run visible."""

    def __init__(self, existing_ids: list[int], dispatch_creates_run: bool = True):
        self._runs = [_FakeRun(run_id) for run_id in existing_ids]
        self._next_id = max(existing_ids, default=0) + 1
        self._dispatch_creates_run = dispatch_creates_run
        self.dispatches: list[dict[str, Any]] = []

    def get_runs(self, *, branch: str, event: str) -> list[_FakeRun]:
        return list(self._runs)

    def create_dispatch(self, *, ref: str, inputs: dict[str, Any], throw: bool = True) -> None:
        self.dispatches.append({"ref": ref, "inputs": inputs})
        if self._dispatch_creates_run:
            self._runs.insert(0, _FakeRun(self._next_id))


class _FakeRepo:
    """Stands in for a PyGithub repository, over the fakes it hands out."""

    def __init__(self, workflow: _FakeWorkflow | None = None, run: _FakeRun | None = None):
        self._workflow = workflow
        self._run = run

    def get_workflow(self, path: str) -> _FakeWorkflow:
        assert self._workflow is not None, "not configured for get_workflow"
        return self._workflow

    def get_workflow_run(self, run_id: int) -> _FakeRun:
        assert self._run is not None, "not configured for get_workflow_run"
        return self._run


def _fake_client(repo: _FakeRepo) -> Any:
    class _FakeGithub:
        def get_repo(self, path: str) -> _FakeRepo:
            return repo

    return _FakeGithub()


@pytest.fixture(name="no_sleep")
def no_sleep_fixture(monkeypatch):
    """Make helper poll loops instant: they sleep between polls by design."""
    monkeypatch.setattr(time, "sleep", lambda seconds: None)


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


def test_dispatch_workflow_returns_the_new_run_id(no_sleep):
    """
    arrange: A workflow with two pre-existing dispatch runs, whose next dispatch makes
        a new run visible at the head of the listing.
    act: Dispatch through dispatch_workflow.
    assert: The new run's id is returned -- not a pre-existing one -- and the dispatch
        carried the ref and inputs it was given, so a caller can wait on exactly the
        run it caused.
    """
    workflow = _FakeWorkflow(existing_ids=[101, 102])
    client = _fake_client(_FakeRepo(workflow=workflow))

    run_id = dispatch_workflow(
        github_client=client,
        repo_path="canonical/github-runner-operators",
        workflow_path=".github/workflows/e2e.yaml",
        ref="feature-branch",
        inputs={"runner-label": "e2e-123456"},
    )

    assert run_id == 103
    assert workflow.dispatches == [
        {"ref": "feature-branch", "inputs": {"runner-label": "e2e-123456"}}
    ]


def test_dispatch_workflow_fails_when_the_dispatch_is_rejected(no_sleep):
    """
    arrange: A workflow whose dispatch endpoint answers with a GithubException.
    act: Dispatch through dispatch_workflow.
    assert: It fails rather than returning, so a permissions problem surfaces as the
        dispatch failing -- not later, as a run that never appears.
    """

    class _RejectingWorkflow(_FakeWorkflow):
        def create_dispatch(self, *, ref, inputs, throw=True):
            raise GithubException(403, {"message": "Resource not accessible"}, None)

    workflow = _RejectingWorkflow(existing_ids=[])
    client = _fake_client(_FakeRepo(workflow=workflow))

    with pytest.raises(pytest.fail.Exception, match="dispatch_workflow failed"):
        dispatch_workflow(
            github_client=client,
            repo_path="canonical/github-runner-operators",
            workflow_path=".github/workflows/e2e.yaml",
            ref="feature-branch",
            inputs={},
        )


def test_dispatch_workflow_fails_when_no_run_appears(no_sleep):
    """
    arrange: A workflow whose dispatch succeeds but never makes a new run visible.
    act: Dispatch through dispatch_workflow.
    assert: It fails after the polling window instead of returning a stale id, so a
        dispatch that did not take effect cannot be mistaken for one that did.
    """
    workflow = _FakeWorkflow(existing_ids=[101], dispatch_creates_run=False)
    client = _fake_client(_FakeRepo(workflow=workflow))

    with pytest.raises(pytest.fail.Exception, match="did not produce a new run"):
        dispatch_workflow(
            github_client=client,
            repo_path="canonical/github-runner-operators",
            workflow_path=".github/workflows/e2e.yaml",
            ref="feature-branch",
            inputs={},
        )


def test_wait_for_completion_returns_the_conclusion(no_sleep):
    """
    arrange: A run that is already completed with a conclusion.
    act: Wait for it through wait_for_completion.
    assert: The conclusion is returned. Pairs with the timeout case below: on its own,
        that one is satisfied by an implementation that never returns at all -- a
        deadline computed backwards, say -- because failing is what it expects.
    """
    run = _FakeRun(103, status="completed", conclusion="success")
    client = _fake_client(_FakeRepo(run=run))

    conclusion = wait_for_completion(
        github_client=client,
        repo_path="canonical/github-runner-operators",
        run_id=103,
    )

    assert conclusion == "success"


def test_wait_for_completion_fails_on_timeout(no_sleep):
    """
    arrange: A run that never leaves the queued state, and a zero-second timeout.
    act: Wait for it through wait_for_completion.
    assert: It fails rather than returning, so a hung run surfaces as this wait
        expiring rather than as a None conclusion the caller must remember to check.
    """
    run = _FakeRun(103, status="queued")
    client = _fake_client(_FakeRepo(run=run))

    with pytest.raises(pytest.fail.Exception, match="did not complete within"):
        wait_for_completion(
            github_client=client,
            repo_path="canonical/github-runner-operators",
            run_id=103,
            poll_interval=0,
            timeout=0,
        )
