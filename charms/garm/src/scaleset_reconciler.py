#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaleset reconciler: diffs desired vs observed GARM scalesets and applies changes."""

import logging
from dataclasses import dataclass, field

from garm_api import GarmAuthenticatedClient
from garm_client.models.create_scale_set_params import CreateScaleSetParams
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
    runner_group: str = ""
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
        providers = {p.name for p in self._client.list_providers()}
        observed = {ss.name: ss for ss in self._client.list_scalesets()}

        all_desired_names: set[str] = {spec.name for spec in desired}

        for spec in desired:
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
                self._create(spec, entity_id)

        for name, scaleset in observed.items():
            if name not in all_desired_names:
                logger.info("Deleting orphaned scaleset %s (id=%s)", name, scaleset.id)
                if scaleset.id is not None:
                    self._client.delete_scaleset(scaleset.id)

    def _resolve_entity_id(self, spec: ScalesetSpec) -> str | None:
        """Return the GARM entity UUID for *spec*, or None if not yet registered."""
        if spec.entity_type == "organization":
            return self._client.find_org_id(spec.entity_name)
        if spec.entity_type == "repository":
            return self._client.find_repo_id(spec.entity_name)
        logger.warning("Unknown entity_type %r for scaleset %s", spec.entity_type, spec.name)
        return None

    def _create(self, spec: ScalesetSpec, entity_id: str) -> None:
        extra_specs: dict[str, object] = {}
        if spec.pre_install_scripts:
            extra_specs["pre_install_scripts"] = spec.pre_install_scripts

        params = CreateScaleSetParams.model_validate(
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
        logger.info("Creating scaleset %s under %s %s", spec.name, spec.entity_type, entity_id)
        if spec.entity_type == "organization":
            self._client.create_org_scaleset(entity_id, params)
        else:
            self._client.create_repo_scaleset(entity_id, params)

    def _maybe_update(self, observed, spec: ScalesetSpec) -> None:
        if not self._needs_update(observed, spec):
            logger.debug("Scaleset %s is up to date", spec.name)
            return

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
        self._client.update_scaleset(observed.id, params)

    @staticmethod
    def _needs_update(observed, spec: ScalesetSpec) -> bool:
        observed_scripts = (observed.extra_specs or {}).get("pre_install_scripts", {})
        return (
            observed.image != spec.image
            or observed.flavor != spec.flavor
            or observed.max_runners != spec.max_runners
            or observed.min_idle_runners != spec.min_idle_runners
            or observed.runner_group != (spec.runner_group or None)
            or observed_scripts != spec.pre_install_scripts
        )
