#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaleset reconciler: diffs desired vs observed GARM scalesets and applies changes."""

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from charm_state import RunnerConfig
from garm_api import GarmApiError, GarmAuthenticatedClient, GarmUnauthorizedError
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.instance import Instance
from garm_client.models.scale_set import ScaleSet
from garm_client.models.template import Template
from garm_client.models.update_scale_set_params import UpdateScaleSetParams
from runner_template import build_template_data, render_aproxy_pre_install_script

logger = logging.getLogger(__name__)

# GARM seeds a non-editable system template per forge/OS; we copy this one to
# build per-scaleset runner templates carrying the operator's runner options.
SYSTEM_TEMPLATE_NAME = "github_linux"

# GARM runs pre-install scripts in lexicographic key order; "00-aproxy" sorts
# before the configurator's "pre_install.sh", so the proxy is up before any
# operator-supplied script runs.
APROXY_SCRIPT_NAME = "00-aproxy"

# GARM's runner status for a runner that is executing a workflow job, and the
# GitHub job statuses that still hold one. GARM's job status is a closed set
# ("queued", "in_progress", "completed"), so matching the holding ones by name
# means an absent or unrecognised status frees the runner instead of pinning it
# as busy forever — the same way an unrecognised runner status is treated.
RUNNER_STATUS_ACTIVE = "active"
JOB_STATUSES_HOLDING_RUNNER = frozenset({"queued", "in_progress"})

# GARM instance statuses meaning a delete was accepted but has not completed:
# the provider teardown is failing and being retried with a backoff. The forced
# variant belongs here too — dropping it would downgrade an escalation already in
# flight back to a plain delete, so a stuck instance could never clear.
PENDING_DELETE_STATUSES = frozenset({"pending_delete", "pending_force_delete", "deleting"})

# GitHub terminates a job on a self-hosted runner at 5 days — the limit that
# applies to GARM's runners, not the 6 hours GitHub-hosted ones get. A job record
# still claiming a runner past that has to be stale (a dropped completion webhook)
# rather than a job that is genuinely still running. The bound is deliberately the
# real ceiling: undershooting it would delete a runner in the middle of a long but
# legitimate job, which costs more than leaving a scaleset around for longer.
MAX_JOB_RUNTIME = timedelta(days=5)


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
        observed: dict[str, ScaleSet] = {}
        for scaleset in self._client.list_scalesets():
            if not scaleset.name:
                logger.warning("Skipping observed scaleset with missing name (id=%s)", scaleset.id)
                continue
            observed[scaleset.name] = scaleset

        templates = self._load_templates(desired, observed)
        all_desired_names: set[str] = {spec.name for spec in desired}

        for spec in desired:
            self._reconcile_one(spec, providers, observed, templates)

        for name, scaleset in observed.items():
            if name not in all_desired_names:
                self._delete_orphaned(scaleset)
                self._delete_custom_template(name, templates)

    def _load_templates(
        self, desired: list[ScalesetSpec], observed: dict[str, ScaleSet]
    ) -> dict[str, Template]:
        """Fetch observed templates keyed by name, only when a reconcile pass needs them.

        Args:
            desired: The full desired set of scalesets.
            observed: Observed scalesets keyed by name.

        Returns:
            Observed templates keyed by name, or an empty dict when none are needed.
        """
        # Templates are only needed when a spec carries runner options or an
        # existing scaleset already references a custom template (to update or
        # detach it); skip the API call entirely otherwise.
        templates: dict[str, Template] = {}
        if any(spec.runner_config.has_config() for spec in desired) or any(
            scaleset.template_id for scaleset in observed.values()
        ):
            templates = {
                (template.name or ""): template
                for template in self._client.list_templates()
                if template.name
            }
        return templates

    def _reconcile_one(
        self,
        spec: ScalesetSpec,
        providers: set[str | None],
        observed: dict[str, ScaleSet],
        templates: dict[str, Template],
    ) -> None:
        """Reconcile a single desired scaleset: validate, create or update, and sync its template.

        Args:
            spec: The desired scaleset.
            providers: Names of providers currently registered in GARM.
            observed: Observed scalesets keyed by name.
            templates: Observed templates keyed by name.
        """
        try:
            create_params = self._to_create_params(spec)
        except Exception as exc:
            logger.warning("Skipping scaleset %s: spec validation failed: %s", spec.name, exc)
            return

        if spec.provider_name not in providers:
            logger.warning(
                "Skipping scaleset %s: provider %s not registered yet",
                spec.name,
                spec.provider_name,
            )
            return

        entity_id = self._resolve_entity_id(spec)
        if entity_id is None:
            logger.warning(
                "Skipping scaleset %s: %s '%s' not registered in GARM yet",
                spec.name,
                spec.entity_type,
                spec.entity_name,
            )
            return

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

    def _delete_orphaned(self, scaleset: ScaleSet) -> None:
        """Disable, drain, then delete a scaleset that is no longer in the desired set."""
        name = scaleset.name or ""
        logger.info("Deleting orphaned scaleset %s (id=%s)", name, scaleset.id)
        if scaleset.id is None:
            return
        forge_reachable = self._disable(scaleset.id, name)
        if forge_reachable is not None:
            # GARM returns 400 while the scaleset still owns runners, so the runners
            # have to go first; anything left behind is retried on the next pass.
            self._remove_runners(scaleset.id, name, forge_reachable=forge_reachable)
        try:
            self._client.delete_scaleset(scaleset.id)
        except GarmApiError as exc:
            # Runner removal is asynchronous (the provider still has to tear the
            # instance down), so the scaleset is deleted on a later reconcile
            # pass once GARM has finished cleaning them up.
            logger.warning(
                "Could not delete scaleset %s (runners may still be active; "
                "will retry on next reconcile): %s",
                name,
                exc,
            )

    def _disable(self, scaleset_id: int, name: str) -> bool | None:
        """Stop a scaleset launching runners, before its existing ones are removed.

        Args:
            scaleset_id: Id of the scaleset being deleted.
            name: Name of the scaleset being deleted, for logging.

        Returns:
            None when removing the scaleset's runners should be skipped this pass,
            otherwise whether the forge answered — which decides how far the runner
            state GARM reports can be trusted.

            A failure here is only survivable when the forge is what rejected it:
            GARM cannot replace the runners about to be removed if it cannot reach
            the forge either, and that is the very case the removal is built to
            escalate past. Any other failure leaves a scaleset that is still enabled
            and still sized up, so removing its runners would just have GARM launch
            replacements — churning instances on every pass instead of draining.
        """
        try:
            self._client.update_scaleset(
                scaleset_id, UpdateScaleSetParams(enabled=False, min_idle_runners=0)
            )
            return True
        except GarmUnauthorizedError as exc:
            logger.warning(
                "Could not disable scaleset %s before delete: the forge rejected the request"
                " as unauthorized. Removing its runners anyway, since GARM cannot launch"
                " replacements while the forge is unreachable: %s",
                name,
                exc,
            )
            return False
        except GarmApiError as exc:
            logger.warning(
                "Could not disable scaleset %s; leaving its runners in place so GARM does not"
                " replace them while it is still enabled (will retry on next reconcile): %s",
                name,
                exc,
            )
            return None

    def _remove_runners(self, scaleset_id: int, name: str, forge_reachable: bool) -> None:
        """Remove every runner belonging to a scaleset being deleted.

        Args:
            scaleset_id: Id of the scaleset being deleted.
            name: Name of the scaleset being deleted, for logging.
            forge_reachable: Whether the forge answered when the scaleset was
                disabled. When it did not, GARM cannot refresh what its runners are
                doing, so a runner that looks busy may simply be frozen that way.
        """
        try:
            instances = self._client.list_scale_set_instances(scaleset_id)
        except GarmApiError as exc:
            logger.warning(
                "Could not list runners of scaleset %s (will retry on next reconcile): %s",
                name,
                exc,
            )
            return
        # GARM's delete endpoint has no atomic "delete-if-idle" precondition, so a job
        # assigned to an instance between this list and its delete below is a residual
        # race this loop cannot close; it relies on the next reconcile to catch it.
        for instance in instances:
            if not instance.name:
                logger.warning(
                    "Skipping runner with missing name in scaleset %s (id=%s)", name, instance.id
                )
                continue
            if _is_running_job(instance):
                # Deleting the runner here would fail the workflow job running on
                # it, so it is left to finish and removed on a later pass along
                # with the scaleset — which the disable above has already stopped
                # sizing up, so no replacement is launched behind it.
                if forge_reachable:
                    logger.info(
                        "Leaving runner %s of scaleset %s in place: still running a job"
                        " (will retry on the next reconcile)",
                        instance.name,
                        name,
                    )
                else:
                    # GARM learns what a runner is doing from the forge, so with the
                    # forge unreachable this runner stays "busy" on every pass and the
                    # scaleset can never be drained. The runner's own job reports to
                    # GitHub with its registration token rather than GARM's credential,
                    # so it may well still be working — deleting it on a state GARM
                    # cannot confirm risks failing a live job. Say what is stuck and
                    # why instead, since restoring the credentials is what clears it.
                    logger.warning(
                        "Cannot drain scaleset %s: runner %s last reported running a job and"
                        " the forge is unreachable, so GARM cannot confirm whether it still"
                        " is. The scaleset stays until its credentials are valid again.",
                        name,
                        instance.name,
                    )
                continue
            self._delete_runner(instance, name)

    def _delete_runner(self, instance: Instance, scaleset_name: str) -> None:
        """Delete one runner, escalating past a stuck provider or an unauthorized forge.

        Both escalations are withheld until their failure is proven, because each one
        trades a stuck runner for an orphaned resource nothing points at any more:

        * ``force_remove`` makes GARM drop the runner from its database even when the
          provider teardown fails, leaving the instance running in the cloud with no
          record of it. A plain delete instead retries the teardown with a backoff
          indefinitely, so it is only forced once the instance is already sitting in
          a pending-delete state — GARM accepted an earlier delete and has not managed
          to carry it out.
        * ``bypass_gh_unauthorized`` drops the runner from the provider and GARM's
          database without deregistering it in GitHub, orphaning it there. It is
          reserved for a 401 — the only status GARM returns for an unauthorized forge
          error. Any other failure (a connection error, a 5xx, or a 400 for a runner
          that is not yet in a deletable state) is transient, so it is left for the
          next reconcile rather than escalated into a GitHub orphan.

        Args:
            instance: The runner instance to delete.
            scaleset_name: Name of the owning scaleset, for logging.
        """
        instance_name = instance.name or ""
        force_remove = _is_delete_stuck(instance)
        logger.info(
            "Removing runner %s from orphaned scaleset %s (force=%s)",
            instance_name,
            scaleset_name,
            force_remove,
        )
        try:
            self._client.delete_instance(instance_name, force_remove=force_remove)
            return
        except GarmUnauthorizedError as exc:
            logger.warning(
                "Could not remove runner %s: GitHub rejected the request as unauthorized;"
                " retrying with the bypass (this may leave the runner registered in"
                " GitHub, where it must be removed manually): %s",
                instance_name,
                exc,
            )
        except GarmApiError as exc:
            self._log_deferred_runner_delete(instance_name, exc)
            return
        try:
            self._client.delete_instance(
                instance_name, force_remove=force_remove, bypass_gh_unauthorized=True
            )
        except GarmApiError as exc:
            self._log_deferred_runner_delete(instance_name, exc)

    @staticmethod
    def _log_deferred_runner_delete(instance_name: str, exc: GarmApiError) -> None:
        logger.warning(
            "Could not remove runner %s (will retry on next reconcile): %s", instance_name, exc
        )

    def _resolve_entity_id(self, spec: ScalesetSpec) -> str | None:
        """Return the GARM entity UUID for *spec*, or None if not yet registered."""
        if spec.entity_type == "organization":
            return self._client.find_org_id(spec.entity_name)
        if spec.entity_type == "repository":
            return self._client.find_repo_id(spec.entity_name)
        logger.warning("Unknown entity_type %r for scaleset %s", spec.entity_type, spec.name)
        return None

    def _ensure_template(self, spec: ScalesetSpec, templates: dict[str, Template]) -> int:
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
                return existing.id or 0
            logger.warning(
                "System template %s not found; scaleset %s will use the default template",
                SYSTEM_TEMPLATE_NAME,
                spec.name,
            )
            return 0

        new_data = build_template_data(self._template_bytes(base), spec.runner_config)
        if existing is not None:
            if existing.id is None:
                logger.warning(
                    "Runner template %s has no id; scaleset %s will use the default template",
                    custom_name,
                    spec.name,
                )
                return 0
            if self._template_bytes(existing) != new_data:
                logger.info("Updating runner template %s", custom_name)
                self._client.update_template(existing.id, data=new_data)
            return existing.id

        logger.info("Creating runner template %s", custom_name)
        created = self._client.create_template(
            name=custom_name,
            data=new_data,
            description=f"Runner template for scaleset {spec.name}",
        )
        return created.id or 0

    def _template_bytes(self, template: Template) -> bytes:
        """Return a template's raw bytes, fetching the full object if needed.

        Args:
            template: A template, possibly without its ``data`` field populated
                (the list endpoint omits the body).

        Returns:
            The decoded template bytes.
        """
        # data is Any at runtime: the list endpoint omits it, and it can come back
        # as a base64 str or (in tests) the raw list-of-ints byte representation.
        data = getattr(template, "data", None)
        if not data:
            if template.id is None:
                return b""
            fetched = self._client.get_template(template.id)
            data = getattr(fetched, "data", None)
            # Cache it back so repeated lookups don't re-fetch, but only when
            # the generated model can accept the assigned value.
            if isinstance(data, str):
                setattr(template, "data", data)
            if not data:
                return b""
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return base64.b64decode(data)
        return bytes(data)

    def _template_by_id(
        self, templates: dict[str, Template], template_id: int | None
    ) -> Template | None:
        """Return a listed template by id, or None when absent."""
        if template_id is None:
            return None
        return next(
            (template for template in templates.values() if (template.id or 0) == template_id),
            None,
        )

    def _delete_custom_template(self, scaleset_name: str, templates: dict[str, Template]) -> None:
        """Delete a scaleset's custom runner template if one exists.

        Args:
            scaleset_name: The name of the scaleset being removed.
            templates: Observed templates keyed by name.
        """
        custom_name = f"{SYSTEM_TEMPLATE_NAME}-{scaleset_name}"
        custom = templates.get(custom_name)
        if custom is not None:
            if custom.id is None:
                logger.warning("Skipping delete for runner template %s: missing id", custom_name)
                return
            logger.info("Deleting orphaned runner template %s", custom.name or custom_name)
            try:
                self._client.delete_template(custom.id)
            except GarmApiError as exc:
                logger.warning(
                    "Could not delete runner template %s (will retry on next reconcile): %s",
                    custom.name or custom_name,
                    exc,
                )

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
                "enabled": True,
                "labels": sorted(spec.labels),
                "github_runner_group": spec.runner_group or None,
                "extra_specs": _effective_extra_specs(spec) or None,
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

    def _maybe_update(self, observed: ScaleSet, spec: ScalesetSpec, template_id: int) -> None:
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

        # _needs_update already covers the template id (its last clause), so an
        # id change alone forces an update here.
        if not self._needs_update(observed, spec, template_id):
            logger.debug("Scaleset %s is up to date", spec.name)
            return

        # UpdateScaleSetParams omits None fields (exclude_none), so None can only
        # leave extra_specs untouched, never clear them. Send an explicit empty
        # dict when the desired specs are empty but the scaleset still carries
        # some (e.g. a proxy was unset) — otherwise a stale aproxy script would
        # persist and _needs_update would loop forever trying to converge.
        desired_extra = _effective_extra_specs(spec)
        extra_specs = desired_extra or ({} if observed.extra_specs else None)
        params = UpdateScaleSetParams(
            image=spec.image,
            flavor=spec.flavor,
            min_idle_runners=spec.min_idle_runners,
            max_runners=spec.max_runners,
            enabled=True,
            runner_group=spec.runner_group or None,
            extra_specs=extra_specs,
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
        # GARM round-trips extra_specs exactly as sent, so the observed script
        # values are base64 like the desired ones — compare them encoded.
        observed_extra = observed.extra_specs or {}
        desired_extra = _effective_extra_specs(spec)
        return (
            observed.image != spec.image
            or observed.flavor != spec.flavor
            or observed.max_runners != spec.max_runners
            or observed.min_idle_runners != spec.min_idle_runners
            or observed.enabled is not True
            or observed.github_runner_group != (spec.runner_group or None)
            or observed_extra.get("pre_install_scripts", {})
            != desired_extra.get("pre_install_scripts", {})
            or bool(observed_extra.get("disable_updates"))
            != bool(desired_extra.get("disable_updates"))
            or (observed.template_id or 0) != template_id
        )


def _is_running_job(instance: Instance) -> bool:
    """Return whether a runner is currently executing a workflow job.

    GARM does not refuse to delete a busy runner, so the charm has to check before
    force-removing one: tearing down a runner mid-job fails the workflow job.

    Args:
        instance: The runner instance to inspect.

    Returns:
        True when the runner is running a job and must be left alone.
    """
    # "active" is GARM's runner status for a runner executing a job. GARM derives it
    # from the forge's live view of the runner, so it corrects itself once a job ends.
    if (instance.runner_status or "").lower() == RUNNER_STATUS_ACTIVE:
        return True
    # The job field is a second signal, covering the window where the list endpoint
    # reports an assigned job before the runner status catches up. It is only trusted
    # while it is fresh: GARM reconciles stale *queued* jobs against the forge but not
    # in-progress ones, so a dropped completion webhook would otherwise leave a job
    # claiming its runner forever and strand the scaleset the delete is trying to free.
    job = instance.job
    if job is None or (job.status or "").lower() not in JOB_STATUSES_HOLDING_RUNNER:
        return False
    return not _is_stale(job.updated_at)


def _is_delete_stuck(instance: Instance) -> bool:
    """Return whether GARM has a delete for this runner that the provider keeps refusing.

    Args:
        instance: The runner instance to inspect.

    Returns:
        True when a delete has been accepted and the provider reported a fault
        carrying it out. Both halves are needed: a delete-pending status on its own
        is also what a perfectly healthy teardown looks like while it runs, and a
        cloud instance can take minutes to disappear, so forcing on the status alone
        would escalate normal in-flight deletes and turn a retryable failure into a
        leaked instance. GARM records the provider's error against the runner when a
        teardown fails, which is what separates the two.
    """
    if (instance.status or "").lower() not in PENDING_DELETE_STATUSES:
        return False
    return bool(instance.provider_fault)


def _is_stale(updated_at: datetime | None) -> bool:
    """Return whether a job record is too old to still describe a running job.

    Args:
        updated_at: When GARM last updated the job record, if it reported one.

    Returns:
        True when the record is older than the longest a job can run, so it cannot
        describe a live job. An absent or unreadable timestamp is not treated as
        stale: without evidence the record is old, the runner keeps its protection.
    """
    if updated_at is None:
        return False
    # GARM serialises timestamps as RFC 3339, but a naive value would raise on
    # comparison; read it as UTC rather than letting the cleanup fail on it.
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated_at > MAX_JOB_RUNTIME


def _effective_extra_specs(spec: ScalesetSpec) -> dict[str, object]:
    """Build the scaleset extra_specs a spec should produce.

    Single source of truth for create, update, and drift detection: combines the
    operator-supplied pre-install scripts with the charm's aproxy bootstrap and
    the ``disable_updates`` flag when a runner proxy is configured.

    Args:
        spec: The desired scaleset.

    Returns:
        The extra_specs dict, with all script values base64-encoded (GARM decodes
        ``pre_install_scripts`` as ``map[string][]byte``); empty when the spec
        yields no extra specs.
    """
    scripts = dict(spec.pre_install_scripts)
    extra_specs: dict[str, object] = {}
    if spec.runner_config.runner_http_proxy:
        # The aproxy bootstrap must run before GARM's compiled-in install wrapper
        # (which needs egress to fetch the runner template), hence a pre-install
        # script rather than template content.
        scripts[APROXY_SCRIPT_NAME] = render_aproxy_pre_install_script(spec.runner_config)
        # cloud-init's apt upgrade runs before any pre-install script, so it can
        # never use the proxy — skip it instead of timing out on every mirror.
        extra_specs["disable_updates"] = True
    if scripts:
        extra_specs["pre_install_scripts"] = {
            name: base64.b64encode(content.encode("utf-8")).decode("utf-8")
            for name, content in scripts.items()
        }
    return extra_specs
