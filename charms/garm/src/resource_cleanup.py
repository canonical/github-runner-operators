# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Idempotent cleanup of GARM resources before charm removal."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from garm_api import GarmApiError, GarmNotFoundError
from garm_client.models.update_scale_set_params import UpdateScaleSetParams

logger = logging.getLogger(__name__)

# GARM only accepts runner deletion for these states. Runners in creation or
# already being deleted are observed again on a later cleanup pass.
_DELETABLE_RUNNER_STATES = frozenset({
    "running",
    "error",
})


class GarmCleanupError(GarmApiError):
    """Raised when GARM resources could not be drained before the deadline."""


class GarmResourceCleanup:
    """Drain all GARM scalesets and runners using observed state.

    The operation is deliberately retryable: runner deletion is asynchronous,
    so a scaleset is deleted only after a later poll observes no instances.
    """

    def __init__(
        self,
        client: Any,
        *,
        timeout: float = 120.0,
        poll_interval: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        force_remove: bool = False,
        bypass_gh_unauthorized: bool = False,
    ) -> None:
        self._client = client
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._force_remove = force_remove
        self._bypass_gh_unauthorized = bypass_gh_unauthorized

    def run(self) -> None:
        """Drain resources, or raise if the cleanup deadline is reached."""
        deadline = self._monotonic() + self._timeout
        last_errors: list[str] = []

        while True:
            pending, errors = self._drain_pass()
            if not pending:
                return

            last_errors = errors or last_errors
            if self._monotonic() >= deadline:
                details = "; ".join(last_errors) if last_errors else "resources remain"
                message = (
                    "GARM cleanup did not complete before the deadline. "
                    f"Blocking resources and errors: {details}. "
                    "Operator action: resolve the listed runner/provider/API issues, "
                    "then retry Juju application removal."
                )
                logger.error(message)
                raise GarmCleanupError(message)
            self._sleep(self._poll_interval)

    def _drain_pass(self) -> tuple[bool, list[str]]:
        """Perform one observed-state cleanup pass."""
        try:
            scalesets = list(self._client.list_scalesets() or [])
        except GarmApiError as exc:
            detail = (
                f"listing scalesets: {exc}; "
                "operator action: verify GARM is reachable and credentials are valid, "
                "then retry removal"
            )
            logger.warning("GARM cleanup is blocked: %s", detail)
            return True, [detail]

        pending = False
        errors: list[str] = []
        for scaleset in scalesets:
            scaleset_pending, scaleset_errors = self._drain_scaleset(scaleset)
            pending = pending or scaleset_pending
            errors.extend(scaleset_errors)
        return pending, errors

    def _drain_scaleset(self, scaleset: Any) -> tuple[bool, list[str]]:
        """Disable and drain one scaleset, returning whether another pass is needed."""
        scaleset_id = getattr(scaleset, "id", None)
        if scaleset_id is None:
            return True, ["observed scaleset has no id"]

        try:
            # Disabling before instance deletion prevents new runners from
            # appearing while this drain is in progress.
            self._client.update_scaleset(
                scaleset_id,
                UpdateScaleSetParams(enabled=False, min_idle_runners=0),
            )
            instances = list(self._client.list_scale_set_instances(scaleset_id) or [])
        except GarmNotFoundError:
            # Another cleanup pass or operator already removed the scaleset.
            return False, []
        except GarmApiError as exc:
            detail = (
                f"scaleset {scaleset_id}: {exc}; "
                "operator action: inspect the scaleset and GARM API/provider health, "
                "then retry removal"
            )
            logger.warning("GARM cleanup is blocked: %s", detail)
            return True, [detail]

        if instances:
            details = self._describe_blocking_instances(scaleset_id, instances)
            errors = [details, *self._delete_eligible_instances(instances)]
            # Runner deletion is asynchronous; always wait for the next pass
            # before attempting to delete the scaleset.
            return True, errors

        try:
            self._client.delete_scaleset(scaleset_id)
        except GarmNotFoundError:
            return False, []
        except GarmApiError as exc:
            detail = (
                f"scaleset {scaleset_id}: {exc}; "
                "operator action: inspect the scaleset's GitHub/provider state, "
                "then retry removal"
            )
            logger.warning("GARM cleanup is blocked: %s", detail)
            return True, [detail]
        return False, []

    @staticmethod
    def _describe_blocking_instances(scaleset_id: int, instances: list[Any]) -> str:
        """Describe remaining instances and the action needed to unblock removal."""
        descriptions = []
        for instance in instances:
            name = getattr(instance, "name", None) or "<unnamed>"
            state = getattr(instance, "status", None) or "<unknown>"
            if state in {"creating", "pending_create"}:
                action = "inspect the runner state and provider operation"
            elif state in {"pending_delete", "pending_force_delete", "deleting", "deleted"}:
                action = "wait for the GARM deletion worker or inspect its logs"
            else:
                action = "inspect the runner state in GARM"
            descriptions.append(
                f"runner {name} status={state} "
                f"(operator action: {action}, then retry removal)"
            )
        return (
            f"scaleset {scaleset_id} has {len(instances)} blocking runner(s): "
            + ", ".join(descriptions)
        )

    def _delete_eligible_instances(self, instances: list[Any]) -> list[str]:
        """Request deletion for eligible instances without aborting the pass."""
        errors: list[str] = []
        for instance in instances:
            name = getattr(instance, "name", None)
            state = getattr(instance, "status", None)
            if not name or state not in _DELETABLE_RUNNER_STATES:
                continue
            try:
                self._client.delete_instance(
                    name,
                    force_remove=self._force_remove,
                    bypass_gh_unauthorized=self._bypass_gh_unauthorized,
                )
            except GarmNotFoundError:
                # The runner disappeared between listing and deletion.
                continue
            except GarmApiError as exc:
                detail = (
                    f"runner {name} status={state}: {exc}; "
                    "operator action: inspect the runner's GitHub/provider state "
                    "and credentials, then retry removal"
                )
                logger.warning("GARM cleanup is blocked: %s", detail)
                errors.append(detail)
        return errors
