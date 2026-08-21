# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Idempotent cleanup of GARM resources before charm removal."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from garm_api import GarmApiError
from garm_client.models.update_scale_set_params import UpdateScaleSetParams

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
                raise GarmCleanupError(
                    f"GARM cleanup did not complete before the deadline: {details}"
                )
            self._sleep(self._poll_interval)

    def _drain_pass(self) -> tuple[bool, list[str]]:
        """Perform one observed-state cleanup pass."""
        try:
            scalesets = list(self._client.list_scalesets() or [])
        except GarmApiError as exc:
            return True, [f"listing scalesets: {exc}"]

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
        except GarmApiError as exc:
            return True, [f"scaleset {scaleset_id}: {exc}"]

        if instances:
            errors = self._delete_eligible_instances(instances)
            # Runner deletion is asynchronous; always wait for the next pass
            # before attempting to delete the scaleset.
            return True, errors

        try:
            self._client.delete_scaleset(scaleset_id)
        except GarmApiError as exc:
            return True, [f"scaleset {scaleset_id}: {exc}"]
        return False, []

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
            except GarmApiError as exc:
                errors.append(f"runner {name}: {exc}")
        return errors
