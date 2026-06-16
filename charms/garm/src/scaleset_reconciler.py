#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaleset reconciler: diffs desired vs observed GARM scalesets and applies changes."""

import logging
from dataclasses import dataclass, field

from garm_api import GarmClient

logger = logging.getLogger(__name__)


@dataclass
class ScalesetSpec:
    """Desired state for one GARM scaleset."""

    name: str
    provider_name: str
    credentials_name: str
    image_id: str
    flavor: str
    os_arch: str
    min_idle_runners: int
    max_runners: int
    labels: list[str] = field(default_factory=list)
    runner_group: str = "default"
    pre_install_scripts: dict[str, str] = field(default_factory=dict)


class ScalesetReconciler:
    """Reconciles GARM scalesets against a desired spec list."""

    def __init__(self, client: GarmClient) -> None:
        """Initialise the reconciler.

        Args:
            client: Authenticated GarmClient instance.
        """
        self._client = client

    def reconcile(self, desired: list[ScalesetSpec]) -> None:
        """Sync GARM scalesets to match *desired*.

        Performs the minimum set of CREATE / UPDATE / DELETE operations.
        If a referenced provider or credential is missing for a spec, that
        spec is skipped silently (deferred creation) — no error state is set.

        Args:
            desired: The full desired set of scalesets.
        """
        providers = {provider["name"] for provider in self._client.list_providers()}
        credentials = {credential["name"] for credential in self._client.list_credentials()}
        observed = {scaleset["name"]: scaleset for scaleset in self._client.list_scalesets()}

        desired_names: set[str] = set()

        for spec in desired:
            if spec.provider_name not in providers:
                logger.warning(
                    "Skipping scaleset %s: provider %s not registered yet",
                    spec.name,
                    spec.provider_name,
                )
                continue
            if spec.credentials_name not in credentials:
                logger.warning(
                    "Skipping scaleset %s: credential %s not registered yet",
                    spec.name,
                    spec.credentials_name,
                )
                continue

            desired_names.add(spec.name)

            if spec.name in observed:
                self._maybe_update(observed[spec.name], spec)
            else:
                self._create(spec)

        for name, scaleset in observed.items():
            if name not in desired_names:
                logger.info("Deleting orphaned scaleset %s (id=%s)", name, scaleset["id"])
                self._client.delete_scaleset(scaleset["id"])

    def _create(self, spec: ScalesetSpec) -> None:
        extra_specs: dict[str, object] = {}
        if spec.pre_install_scripts:
            extra_specs["pre_install_scripts"] = spec.pre_install_scripts

        payload = {
            "name": spec.name,
            "provider_name": spec.provider_name,
            "credentials_name": spec.credentials_name,
            "image_id": spec.image_id,
            "flavor": spec.flavor,
            "os_arch": spec.os_arch,
            "min_idle_runners": spec.min_idle_runners,
            "max_runners": spec.max_runners,
            "tags": sorted(spec.labels),
            "runner_group": spec.runner_group,
            "extra_specs": extra_specs,
        }
        logger.info("Creating scaleset %s", spec.name)
        self._client.create_scaleset(payload)

    def _maybe_update(self, observed: dict, spec: ScalesetSpec) -> None:
        if not self._needs_update(observed, spec):
            logger.debug("Scaleset %s is up to date", spec.name)
            return

        extra_specs: dict[str, object] = {}
        if spec.pre_install_scripts:
            extra_specs["pre_install_scripts"] = spec.pre_install_scripts

        payload = {
            "image_id": spec.image_id,
            "flavor": spec.flavor,
            "min_idle_runners": spec.min_idle_runners,
            "max_runners": spec.max_runners,
            "tags": sorted(spec.labels),
            "runner_group": spec.runner_group,
            "extra_specs": extra_specs,
        }
        logger.info("Updating scaleset %s (id=%s)", spec.name, observed["id"])
        self._client.update_scaleset(observed["id"], payload)

    @staticmethod
    def _needs_update(observed: dict, spec: ScalesetSpec) -> bool:
        observed_scripts = (observed.get("extra_specs") or {}).get("pre_install_scripts", {})
        return (
            observed.get("image_id") != spec.image_id
            or observed.get("flavor") != spec.flavor
            or observed.get("max_runners") != spec.max_runners
            or observed.get("min_idle_runners") != spec.min_idle_runners
            or sorted(observed.get("tags") or []) != sorted(spec.labels)
            or observed.get("runner_group") != spec.runner_group
            or observed_scripts != spec.pre_install_scripts
        )
