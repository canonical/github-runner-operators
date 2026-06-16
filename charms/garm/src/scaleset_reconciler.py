#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaleset reconciler: diffs desired vs observed GARM scalesets and applies changes."""

import base64
import logging
from dataclasses import dataclass, field

from garm_api import GarmClient
from runner_template import RunnerConfig, build_template_data

logger = logging.getLogger(__name__)

# GARM seeds a non-editable system template per forge/OS; we copy this one to
# build per-scaleset runner templates carrying the operator's runner options.
SYSTEM_TEMPLATE_NAME = "github_linux"


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
    runner_config: RunnerConfig = field(default_factory=RunnerConfig)


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

        Performs the minimum set of CREATE / UPDATE / DELETE operations, and
        maintains a per-scaleset runner-install template carrying the runner
        options. If a referenced provider or credential is missing for a spec,
        that spec is skipped silently (deferred creation) — no error state is set.

        Args:
            desired: The full desired set of scalesets.
        """
        providers = {provider["name"] for provider in self._client.list_providers()}
        credentials = {credential["name"] for credential in self._client.list_credentials()}
        observed = {scaleset["name"]: scaleset for scaleset in self._client.list_scalesets()}
        templates = {template["name"]: template for template in self._client.list_templates()}

        all_desired_names: set[str] = {spec.name for spec in desired}

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

            template_id = self._ensure_template(spec, templates)

            if spec.name in observed:
                self._maybe_update(observed[spec.name], spec, template_id)
            else:
                self._create(spec, template_id)

        for name, scaleset in observed.items():
            if name not in all_desired_names:
                logger.info("Deleting orphaned scaleset %s (id=%s)", name, scaleset["id"])
                self._client.delete_scaleset(scaleset["id"])
                self._delete_custom_template(name, templates)

    def _ensure_template(self, spec: ScalesetSpec, templates: dict[str, dict]) -> int | None:
        """Ensure the scaleset's runner template reflects its runner options.

        Copies the system ``github_linux`` template, injects the runner options,
        and creates or updates the per-scaleset template. The template content is
        refreshed in place (same id) on every reconcile, so an option change is
        applied without touching the scaleset itself.

        Args:
            spec: The desired scaleset.
            templates: Observed templates keyed by name.

        Returns:
            The template id to reference from the scaleset, or None to keep the
            default template (no runner options set, or the system template is
            unavailable).
        """
        if not spec.runner_config.has_config():
            return None

        base = templates.get(SYSTEM_TEMPLATE_NAME)
        if base is None:
            logger.warning(
                "System template %s not found; scaleset %s will use the default template",
                SYSTEM_TEMPLATE_NAME,
                spec.name,
            )
            return None

        new_data = build_template_data(self._template_bytes(base), spec.runner_config)
        custom_name = f"{SYSTEM_TEMPLATE_NAME}-{spec.name}"
        existing = templates.get(custom_name)
        if existing is not None:
            if self._template_bytes(existing) != new_data:
                logger.info("Updating runner template %s", custom_name)
                self._client.update_template(existing["id"], data=new_data)
            return existing["id"]

        logger.info("Creating runner template %s", custom_name)
        created = self._client.create_template(
            name=custom_name,
            data=new_data,
            description=f"Runner template for scaleset {spec.name}",
        )
        return created["id"]

    def _template_bytes(self, template: dict) -> bytes:
        """Return a template's raw bytes, fetching the full object if needed.

        Args:
            template: A template dict, possibly without its ``data`` field populated.

        Returns:
            The decoded template bytes.
        """
        data = template.get("data")
        if not data:
            data = self._client.get_template(template["id"]).get("data", "")
        return base64.b64decode(data) if data else b""

    def _delete_custom_template(self, scaleset_name: str, templates: dict[str, dict]) -> None:
        """Delete a scaleset's custom runner template if one exists.

        Args:
            scaleset_name: The name of the scaleset being removed.
            templates: Observed templates keyed by name.
        """
        custom = templates.get(f"{SYSTEM_TEMPLATE_NAME}-{scaleset_name}")
        if custom is not None:
            logger.info("Deleting orphaned runner template %s", custom["name"])
            self._client.delete_template(custom["id"])

    def _create(self, spec: ScalesetSpec, template_id: int | None) -> None:
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
        if template_id is not None:
            payload["template_id"] = template_id
        logger.info("Creating scaleset %s", spec.name)
        self._client.create_scaleset(payload)

    def _maybe_update(self, observed: dict, spec: ScalesetSpec, template_id: int | None) -> None:
        template_changed = template_id is not None and observed.get("template_id") != template_id
        if not self._needs_update(observed, spec) and not template_changed:
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
        if template_id is not None:
            payload["template_id"] = template_id
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
