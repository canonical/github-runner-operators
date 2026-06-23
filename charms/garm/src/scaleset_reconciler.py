#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaleset reconciler: diffs desired vs observed GARM scalesets and applies changes."""

import logging
from dataclasses import dataclass, field

from garm_api import GarmApiError, GarmAuthenticatedClient
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.scale_set import ScaleSet
from garm_client.models.update_scale_set_params import UpdateScaleSetParams

logger = logging.getLogger(__name__)


@dataclass
class ScalesetSpec:
    """Desired state for one GARM scaleset."""

    name: str
    provider_name: str
    image: str
    flavor: str
    os_arch: str
    min_idle_runners: int
    max_runners: int
    entity_type: str
    entity_name: str
    labels: list[str] = field(default_factory=list)
    runner_group: str = "Default"
    pre_install_scripts: dict[str, str] = field(default_factory=dict)


class ScalesetReconciler:
    """Reconciles GARM scalesets against a desired spec list."""

    def __init__(self, client: GarmAuthenticatedClient) -> None:
        """Initialise the reconciler.

        Args:
            client: Authenticated GarmAuthenticatedClient instance.
        """
        self._client = client

    def reconcile(self, desired: list[ScalesetSpec]) -> None:
        """Sync GARM scalesets to match *desired*.

        Performs the minimum set of CREATE / UPDATE / DELETE operations.
        If a referenced provider is missing or the target entity (org/repo)
        is not registered in GARM, that spec is skipped silently (deferred
        creation) — no error state is set.

        Args:
            desired: The full desired set of scalesets.
        """
        providers = {provider.name for provider in self._client.list_providers()}
        observed = {scaleset.name: scaleset for scaleset in self._client.list_scalesets()}

        all_desired_names: set[str] = {spec.name for spec in desired}

        for spec in desired:
            try:
                create_params = self._to_create_params(spec)
            except Exception as exc:
                logger.warning("Skipping scaleset %s: spec validation failed: %s", spec.name, exc)
                continue

            if spec.provider_name not in providers:
                logger.warning(
                    "Skipping scaleset %s: provider %s not registered yet",
                    spec.name,
                    spec.provider_name,
                )
                continue

            entity_id = self._resolve_entity_id(spec)
            if entity_id is None:
                logger.warning(
                    "Skipping scaleset %s: %s '%s' not registered in GARM yet",
                    spec.name,
                    spec.entity_type,
                    spec.entity_name,
                )
                continue

            if spec.name in observed:
                self._maybe_update(observed[spec.name], spec)
            else:
                self._create(spec, entity_id, create_params)

        for name, scaleset in observed.items():
            if name not in all_desired_names:
                self._delete_orphaned(scaleset)

    def _delete_orphaned(self, scaleset: ScaleSet) -> None:
        """Disable then delete a scaleset that is no longer in the desired set."""
        name = scaleset.name or ""
        logger.info("Deleting orphaned scaleset %s (id=%s)", name, scaleset.id)
        if scaleset.id is None:
            return
        try:
            # Disable the scaleset first so GARM stops launching new runners.
            # GARM returns 400 if the scaleset still has active runners,
            # so disabling first drains it for the next reconcile to clean up.
            self._client.update_scaleset(
                scaleset.id, UpdateScaleSetParams(enabled=False, min_idle_runners=0)
            )
        except GarmApiError as exc:
            logger.warning("Could not disable scaleset %s before delete: %s", name, exc)
        try:
            self._client.delete_scaleset(scaleset.id)
        except GarmApiError as exc:
            # 400 means runners are still present; scaleset will be deleted
            # on the next reconcile pass once GARM has cleaned them up.
            logger.warning(
                "Could not delete scaleset %s (runners may still be active; "
                "will retry on next reconcile): %s",
                name,
                exc,
            )

    def _resolve_entity_id(self, spec: ScalesetSpec) -> str | None:
        """Return the GARM entity UUID for *spec*, or None if not yet registered."""
        if spec.entity_type == "organization":
            return self._client.find_org_id(spec.entity_name)
        if spec.entity_type == "repository":
            return self._client.find_repo_id(spec.entity_name)
        logger.warning("Unknown entity_type %r for scaleset %s", spec.entity_type, spec.name)
        return None

    @staticmethod
    def _to_create_params(spec: ScalesetSpec) -> CreateScaleSetParams:
        """Build and validate CreateScaleSetParams from a ScalesetSpec.

        Args:
            spec: The desired scaleset specification.

        Returns:
            Validated CreateScaleSetParams ready for the GARM API.

        Raises:
            ValidationError: If the spec data fails Pydantic model validation.
        """
        extra_specs: dict[str, object] = {}
        if spec.pre_install_scripts:
            extra_specs["pre_install_scripts"] = spec.pre_install_scripts
        return CreateScaleSetParams.model_validate(
            {
                "name": spec.name,
                "provider_name": spec.provider_name,
                "image": spec.image,
                "flavor": spec.flavor,
                "os_arch": spec.os_arch,
                "min_idle_runners": spec.min_idle_runners,
                "max_runners": spec.max_runners,
                "labels": sorted(spec.labels),
                "github_runner_group": spec.runner_group or None,
                "extra_specs": extra_specs or None,
            }
        )

    def _create(self, spec: ScalesetSpec, entity_id: str, params: CreateScaleSetParams) -> None:
        logger.info("Creating scaleset %s under %s %s", spec.name, spec.entity_type, entity_id)
        if spec.entity_type == "organization":
            self._client.create_org_scaleset(entity_id, params)
        else:
            self._client.create_repo_scaleset(entity_id, params)

    def _maybe_update(self, observed, spec: ScalesetSpec) -> None:
        if not self._needs_update(observed, spec):
            logger.debug("Scaleset %s is up to date", spec.name)
            return

        observed_labels = sorted(t.name for t in (observed.tags or []) if t.name)
        if observed_labels != sorted(spec.labels):
            # UpdateScaleSetParams has no labels field; label changes require
            # recreating the scaleset. Log a warning so operators are aware.
            logger.warning(
                "Scaleset %s labels changed (%s -> %s) but cannot be updated in place;"
                " delete and recreate the scaleset to apply label changes",
                spec.name,
                observed_labels,
                sorted(spec.labels),
            )

        extra_specs: dict[str, object] = {}
        if spec.pre_install_scripts:
            extra_specs["pre_install_scripts"] = spec.pre_install_scripts

        params = UpdateScaleSetParams(
            image=spec.image,
            flavor=spec.flavor,
            min_idle_runners=spec.min_idle_runners,
            max_runners=spec.max_runners,
            runner_group=spec.runner_group or None,
            extra_specs=extra_specs or None,
        )
        logger.info("Updating scaleset %s (id=%s)", spec.name, observed.id)
        if observed.id is None:
            logger.warning("Scaleset %s has no id; skipping update", spec.name)
            return
        self._client.update_scaleset(observed.id, params)

    @staticmethod
    def _needs_update(observed, spec: ScalesetSpec) -> bool:
        observed_scripts = (observed.extra_specs or {}).get("pre_install_scripts", {})
        observed_labels = sorted(t.name for t in (observed.tags or []) if t.name)
        return (
            observed.image != spec.image
            or observed.flavor != spec.flavor
            or observed.max_runners != spec.max_runners
            or observed.min_idle_runners != spec.min_idle_runners
            or observed.github_runner_group != (spec.runner_group or None)
            or observed_scripts != spec.pre_install_scripts
            or observed_labels != sorted(spec.labels)
        )
