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
    image: str
    flavor: str
    os_arch: str
    min_idle_runners: int
    max_runners: int
    entity_type: str
    entity_name: str
    os_type: str = "linux"
    labels: list[str] = field(default_factory=list)
    runner_group: str = "Default"
    pre_install_scripts: dict[str, str] = field(default_factory=dict)
    template_id: int | None = None
    runner_config: RunnerConfig = field(default_factory=RunnerConfig)


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

        Performs the minimum set of CREATE / UPDATE / DELETE operations, and
        maintains a per-scaleset runner-install template carrying the runner
        options. If a referenced provider is missing or the target entity
        (org/repo) is not registered in GARM, that spec is skipped silently
        (deferred creation) — no error state is set.

        Args:
            desired: The full desired set of scalesets.
        """
        providers = {provider.name for provider in self._client.list_providers()}
        observed = {
            (scaleset.name or ""): scaleset for scaleset in self._client.list_scalesets()
        }

        # Templates are only needed when a spec carries runner options or an
        # existing scaleset already references a custom template (to update or
        # detach it); skip the API call entirely otherwise. When fetched, filter
        # by partial name so we only pull the system github_linux template and our
        # per-scaleset github_linux-<name> copies.
        templates: dict[str, object] = {}
        if any(spec.runner_config.has_config() for spec in desired) or any(
            scaleset.template_id for scaleset in observed.values()
        ):
            templates = {
                (template.name or ""): template
                for template in self._client.list_templates(partial_name=SYSTEM_TEMPLATE_NAME)
                if template.name
            }

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

            template_id = self._ensure_template(spec, templates)

            if spec.name in observed:
                self._maybe_update(observed[spec.name], spec, template_id)
            else:
                self._create(spec, entity_id, create_params, template_id)

            if not spec.runner_config.has_config():
                # Runner options were cleared (or the system template is
                # unavailable): the scaleset has been reverted to the default
                # template above, so drop any now-unreferenced custom template.
                self._delete_custom_template(spec.name, templates)

        for name, scaleset in observed.items():
            if name not in all_desired_names:
                self._delete_orphaned(scaleset)
                self._delete_custom_template(name, templates)

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

    def _ensure_template(self, spec: ScalesetSpec, templates: dict[str, object]) -> int:
        """Ensure the scaleset's runner template reflects its runner options.

        Copies the system ``github_linux`` template, injects the runner options,
        and creates or updates the per-scaleset template. The template content is
        refreshed in place (same id) on every reconcile, so an option change is
        applied without touching the scaleset itself.

        Args:
            spec: The desired scaleset.
            templates: Observed templates keyed by name.

        Returns:
            The custom template id to reference from the scaleset, or ``0`` to use
            GARM's default template (no runner options set, or the system template
            is unavailable and no custom template already exists). Returning ``0``
            for a scaleset that previously had a custom template detaches it.
        """
        custom_name = f"{SYSTEM_TEMPLATE_NAME}-{spec.name}"
        existing = templates.get(custom_name)

        if not spec.runner_config.has_config():
            return spec.template_id or 0

        base = self._template_by_id(templates, spec.template_id) or templates.get(
            SYSTEM_TEMPLATE_NAME
        )
        if base is None:
            # The system template is not listed (transient/compat). Don't destroy
            # an existing custom template over it — keep the last-rendered one
            # rather than detaching and losing the runner config; only fall back
            # to the default when there is nothing to keep.
            if existing is not None:
                logger.warning(
                    "System template %s not found; keeping existing custom template for %s",
                    SYSTEM_TEMPLATE_NAME,
                    spec.name,
                )
                return self._template_id(existing)
            logger.warning(
                "System template %s not found; scaleset %s will use the default template",
                SYSTEM_TEMPLATE_NAME,
                spec.name,
            )
            return 0

        new_data = build_template_data(self._template_bytes(base), spec.runner_config)
        if existing is not None:
            if self._template_bytes(existing) != new_data:
                logger.info("Updating runner template %s", custom_name)
                self._client.update_template(self._template_id(existing), data=new_data)
            return self._template_id(existing)

        logger.info("Creating runner template %s", custom_name)
        created = self._client.create_template(
            name=custom_name,
            data=new_data,
            description=f"Runner template for scaleset {spec.name}",
        )
        return created.id or 0

    def _template_bytes(self, template: object) -> bytes:
        """Return a template's raw bytes, fetching the full object if needed.

        Args:
            template: A template object, possibly without its ``data`` field populated.

        Returns:
            The decoded template bytes.
        """
        data = getattr(template, "data", None)
        if not data:
            template_id = getattr(template, "id", None)
            if template_id is None:
                return b""
            fetched = self._client.get_template(template_id)
            fetched_data = getattr(fetched, "data", None) or []
            # Cache it back so repeated lookups don't re-fetch.
            setattr(template, "data", fetched_data)
            data = fetched_data
        return bytes(data)

    def _template_id(self, template: object) -> int:
        """Return the template's id, defaulting to 0 when absent."""
        return getattr(template, "id", None) or 0

    def _template_by_id(
        self, templates: dict[str, object], template_id: int | None
    ) -> object | None:
        """Return a listed template by id, or None when absent."""
        if template_id is None:
            return None
        return next(
            (
                template
                for template in templates.values()
                if self._template_id(template) == template_id
            ),
            None,
        )

    def _delete_custom_template(self, scaleset_name: str, templates: dict[str, object]) -> None:
        """Delete a scaleset's custom runner template if one exists.

        Args:
            scaleset_name: The name of the scaleset being removed.
            templates: Observed templates keyed by name.
        """
        custom = templates.get(f"{SYSTEM_TEMPLATE_NAME}-{scaleset_name}")
        if custom is not None:
            custom_name = getattr(custom, "name", f"{SYSTEM_TEMPLATE_NAME}-{scaleset_name}")
            logger.info("Deleting orphaned runner template %s", custom_name)
            self._client.delete_template(self._template_id(custom))

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
                "os_type": spec.os_type,
                "min_idle_runners": spec.min_idle_runners,
                "max_runners": spec.max_runners,
                "labels": sorted(spec.labels),
                "github_runner_group": spec.runner_group or None,
                "extra_specs": extra_specs or None,
                "template_id": spec.template_id,
            }
        )

    def _create(
        self,
        spec: ScalesetSpec,
        entity_id: str,
        params: CreateScaleSetParams,
        template_id: int,
    ) -> None:
        if template_id:
            params.template_id = template_id
        logger.info("Creating scaleset %s under %s %s", spec.name, spec.entity_type, entity_id)
        if spec.entity_type == "organization":
            self._client.create_org_scaleset(entity_id, params)
        else:
            self._client.create_repo_scaleset(entity_id, params)

    def _maybe_update(
        self, observed: ScaleSet, spec: ScalesetSpec, template_id: int
    ) -> None:
        observed_labels = sorted(t.name for t in (observed.tags or []) if t.name)
        if observed_labels != sorted(spec.labels):
            # UpdateScaleSetParams has no labels field; label changes require
            # recreating the scaleset. To delete a scaleset, remove the
            # garm-configurator relation for the corresponding unit.
            logger.warning(
                "Scaleset %s labels changed (%s -> %s) but cannot be updated in place;"
                " to apply label changes, remove and re-add the garm-configurator relation"
                " for this unit",
                spec.name,
                observed_labels,
                sorted(spec.labels),
            )

        observed_template_id = observed.template_id or 0
        template_changed = observed_template_id != template_id

        if not self._needs_update(observed, spec, template_id) and not template_changed:
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
            template_id=spec.template_id,
        )
        # Send template_id when the scaleset has, or had, a custom template — a 0
        # value detaches it (reverts to the default); omit it otherwise so an
        # unrelated update never spuriously sets the field.
        if template_id or observed_template_id:
            params.template_id = template_id
        logger.info("Updating scaleset %s (id=%s)", spec.name, observed.id)
        if observed.id is None:
            logger.warning("Scaleset %s has no id; skipping update", spec.name)
            return
        self._client.update_scaleset(observed.id, params)

    @staticmethod
    def _needs_update(observed: ScaleSet, spec: ScalesetSpec, template_id: int) -> bool:
        observed_scripts = (observed.extra_specs or {}).get("pre_install_scripts", {})
        return (
            observed.image != spec.image
            or observed.flavor != spec.flavor
            or observed.max_runners != spec.max_runners
            or observed.min_idle_runners != spec.min_idle_runners
            or observed.github_runner_group != (spec.runner_group or None)
            or observed_scripts != spec.pre_install_scripts
            or (observed.template_id or 0) != template_id
        )
