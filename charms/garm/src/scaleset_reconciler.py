#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Scaleset reconciler: diffs desired vs observed GARM scalesets and applies changes."""

import base64
import datetime
import enum
import hashlib
import logging
import re
from dataclasses import dataclass, field

from charm_state import RunnerConfig
from garm_api import GarmApiError, GarmAuthenticatedClient, GarmConnectionError
from garm_client.models.create_scale_set_params import CreateScaleSetParams
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

LABEL_HASH_LENGTH = 8

# GitHub rejects over-long scale set names; keep the generated name inside a
# conservative bound by truncating the operator-supplied part, never the hash.
MAX_SCALESET_NAME_LENGTH = 64

# Past GitHub's 6h job cap a remaining runner is stuck, not busy: stop gating on the
# count and retry the delete, which GARM rejects while runners are active.
DRAIN_DEADLINE = datetime.timedelta(hours=7)


class Handover(enum.Enum):
    """How far the routing hand-over from a replaced generation has got.

    Attributes:
        PENDING: The replacement is not up yet, so the predecessor must stay enabled.
        FAILED: GARM refused to disable the predecessor; the next reconcile retries.
        DONE: The predecessor is disabled and the replacement holds their shared labels.
    """

    # Both unfinished states leave the predecessor enabled and serving jobs, so nothing
    # is draining yet and the runner count reported alongside them is 0.
    PENDING = "pending"
    FAILED = "failed"
    DONE = "done"


@dataclass(frozen=True)
class ScalesetProgress:
    """A scaleset replacement still in flight: the generation it replaced is not gone yet."""

    logical_name: str
    retiring_name: str
    replacement_name: str
    remaining_runners: int
    handover: Handover = Handover.DONE


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


def _name_base(logical_name: str) -> str:
    """Return the part of a live scaleset name that precedes the label hash.

    Args:
        logical_name: The scaleset name the operator configured.

    Returns:
        The name itself when it fits, else a truncation ending in a hash of the full
        name — two long names sharing a prefix would otherwise collapse onto one live
        scaleset and fight over it on every reconcile.
    """
    limit = MAX_SCALESET_NAME_LENGTH - LABEL_HASH_LENGTH - 1
    if len(logical_name) <= limit:
        return logical_name
    digest = hashlib.sha256(logical_name.encode("utf-8")).hexdigest()[:LABEL_HASH_LENGTH]
    return f"{logical_name[: limit - LABEL_HASH_LENGTH - 1]}-{digest}"


def target_scaleset_name(logical_name: str, labels: list[str]) -> str:
    """Return the live GARM name a spec's scaleset should have.

    Args:
        logical_name: The scaleset name the operator configured.
        labels: The desired labels.

    Returns:
        ``<name>-<label hash>``. Only the labels feed the hash: every other spec
        field is updatable in place and must not trigger a recreate.
    """
    digest = hashlib.sha256(",".join(sorted(labels)).encode("utf-8")).hexdigest()
    return f"{_name_base(logical_name)}-{digest[:LABEL_HASH_LENGTH]}"


def _family_pattern(logical_name: str) -> re.Pattern[str]:
    """Return the regex matching every generation of *logical_name*."""
    return re.compile(rf"^{re.escape(_name_base(logical_name))}-[0-9a-f]{{{LABEL_HASH_LENGTH}}}$")


def _is_family_member(observed_name: str, logical_name: str) -> bool:
    """Return whether a live scaleset is a generation of *logical_name*.

    Args:
        observed_name: The live scaleset name.
        logical_name: The configured scaleset name.

    Returns:
        True for a hash-suffixed generation, and for the bare *logical_name* itself —
        scalesets created before label-hashed naming carry the un-suffixed name.
    """
    if observed_name == logical_name:
        return True
    return bool(_family_pattern(logical_name).match(observed_name))


def _observed_labels(scaleset: ScaleSet) -> list[str]:
    """Return a scaleset's labels, sorted, for comparison against a spec."""
    return sorted(tag.name for tag in (scaleset.tags or []) if tag.name)


def _drain_deadline_passed(scaleset: ScaleSet) -> bool:
    """Return whether a retired scaleset has been draining longer than any job can last.

    Args:
        scaleset: The retired scaleset.

    Returns:
        True once ``DRAIN_DEADLINE`` has elapsed since GARM last wrote the scaleset —
        which, for a retired one, is the moment it was disabled: the only writes to that
        row while it drains would come from the listener's message handler
        (``SetScaleSetLastMessageID`` / ``SetScaleSetDesiredRunnerCount``), and disabling
        stopped the listener. ``handleAutoScale`` keeps running but writes instances, a
        separate table. False when GARM reports no timestamp: an unknown drain age must
        never read as an expired one.
    """
    retired_at = scaleset.updated_at
    if retired_at is None:
        return False
    if retired_at.tzinfo is None:
        retired_at = retired_at.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc) - retired_at > DRAIN_DEADLINE


def _resolve_active_name(spec: ScalesetSpec, observed: dict[str, ScaleSet]) -> str:
    """Return the live name of the generation that should serve *spec*.

    Args:
        spec: The desired scaleset.
        observed: Observed scalesets keyed by name.

    Returns:
        The label-hashed target name, except when that name does not exist yet and a
        legacy un-suffixed scaleset already carries exactly the desired labels — that
        one is adopted in place, so upgrading the charm doesn't recreate scalesets
        that are already correct.
    """
    target = target_scaleset_name(spec.name, spec.labels)
    if target in observed:
        return target
    legacy = observed.get(spec.name)
    if legacy is not None and _observed_labels(legacy) == sorted(spec.labels):
        return spec.name
    return target


class ScalesetReconciler:
    """Reconciles GARM scalesets against a desired spec list."""

    def __init__(self, client: GarmAuthenticatedClient) -> None:
        """Initialise the reconciler.

        Args:
            client: Authenticated GarmAuthenticatedClient instance.
        """
        self._client = client

    def reconcile(self, desired: list[ScalesetSpec]) -> list[ScalesetProgress]:
        """Sync GARM scalesets to match *desired*.

        Performs the minimum set of CREATE / UPDATE / DELETE operations, and
        maintains a per-scaleset runner-install template carrying the runner
        options. If a referenced provider is missing or the target entity
        (org/repo) is not registered in GARM, that spec is skipped silently
        (deferred creation) — no error state is set.

        A label change is applied by creating a replacement scaleset and draining
        the old one (see ``_retire_replaced``), which spans several reconciles.

        A spec that fails against the GARM API does not abort the pass: the
        remaining specs and the orphan sweep still run, and the first failure is
        re-raised at the end so the charm still reports the sync as failed. A
        connection error is not contained that way — GARM is down, so retrying
        every remaining spec would only stall the hook.

        Args:
            desired: The full desired set of scalesets.

        Returns:
            One entry per replacement still in flight; empty once converged.

        Raises:
            GarmApiError: If any spec failed to reconcile, re-raised once the rest
                of the pass has completed.
        """
        desired = self._dedupe(desired)
        providers = {provider.name for provider in self._client.list_providers()}
        observed: dict[str, ScaleSet] = {}
        for scaleset in self._client.list_scalesets():
            if not scaleset.name:
                logger.warning("Skipping observed scaleset with missing name (id=%s)", scaleset.id)
                continue
            observed[scaleset.name] = scaleset

        templates = self._load_templates(desired, observed)
        families = self._resolve_families(desired, observed)
        # Covers in-flight replacements and draining predecessors, so the orphan pass
        # can't delete one mid-changeover. Built before the provider/entity gates.
        claimed: set[str] = set()
        for family in families.values():
            claimed.update(family)

        progress: list[ScalesetProgress] = []
        failure: GarmApiError | None = None
        for spec in desired:
            try:
                progress.extend(
                    self._reconcile_one(
                        spec, providers, observed, templates, families.get(spec.name, [])
                    )
                )
            except GarmConnectionError:
                raise
            except GarmApiError as exc:
                logger.warning("Failed to reconcile scaleset %s: %s", spec.name, exc)
                failure = failure or exc

        for name, scaleset in observed.items():
            if name not in claimed and self._delete_orphaned(scaleset):
                self._delete_custom_template(name, templates)
        if failure is not None:
            raise failure
        return progress

    @staticmethod
    def _dedupe(desired: list[ScalesetSpec]) -> list[ScalesetSpec]:
        """Drop specs repeating a logical name already claimed by an earlier one.

        Args:
            desired: The full desired set of scalesets.

        Returns:
            The specs with duplicate names removed, first occurrence winning. Two
            specs sharing a name would each own the other's live scaleset and retire
            it on every reconcile, so they would replace each other forever.
        """
        unique: dict[str, ScalesetSpec] = {}
        for spec in desired:
            existing = unique.get(spec.name)
            if existing is not None:
                # Only a conflicting duplicate is worth a warning: the scaleset config is
                # app-level, so every configurator unit's databag yields the same spec and
                # a multi-unit configurator would otherwise warn on every hook.
                if existing != spec:
                    logger.warning(
                        "Ignoring duplicate desired scaleset %s: a logical name must"
                        " identify exactly one scaleset",
                        spec.name,
                    )
                continue
            unique[spec.name] = spec
        return list(unique.values())

    @staticmethod
    def _resolve_families(
        desired: list[ScalesetSpec], observed: dict[str, ScaleSet]
    ) -> dict[str, list[str]]:
        """Group the live scalesets by the desired spec that owns them.

        Args:
            desired: The full desired set of scalesets.
            observed: Observed scalesets keyed by name.

        Returns:
            Per logical name, every live generation it owns plus its target name
            (which may not exist yet). A live name that is another spec's own or
            target name is never claimed, so ``foo`` can't swallow a separate
            scaleset that happens to be named ``foo-1a2b3c4d``.
        """
        targets = {spec.name: target_scaleset_name(spec.name, spec.labels) for spec in desired}
        reserved = set(targets) | set(targets.values())
        families: dict[str, list[str]] = {}
        for spec in desired:
            others = reserved - {spec.name, targets[spec.name]}
            family = [
                name
                for name in observed
                if name not in others and _is_family_member(name, spec.name)
            ]
            families[spec.name] = sorted({*family, targets[spec.name]})
        return families

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
        family: list[str],
    ) -> list[ScalesetProgress]:
        """Reconcile a single desired scaleset: validate, create or update, and sync its template.

        Args:
            spec: The desired scaleset.
            providers: Names of providers currently registered in GARM.
            observed: Observed scalesets keyed by name.
            templates: Observed templates keyed by name.
            family: Every live generation of this spec, plus its target name.

        Returns:
            One entry per replaced generation of this spec still draining.
        """
        active_name = _resolve_active_name(spec, observed)
        try:
            create_params = self._to_create_params(spec, active_name)
        except Exception as exc:
            # Error, not warning: unlike the provider/entity gates below this does not
            # resolve on its own — the spec is malformed and will fail every pass until
            # the operator changes it.
            logger.error("Skipping scaleset %s: spec validation failed: %s", spec.name, exc)
            return []

        if spec.provider_name not in providers:
            logger.warning(
                "Skipping scaleset %s: provider %s not registered yet",
                spec.name,
                spec.provider_name,
            )
            return []

        entity_id = self._resolve_entity_id(spec)
        if entity_id is None:
            logger.warning(
                "Skipping scaleset %s: %s '%s' not registered in GARM yet",
                spec.name,
                spec.entity_type,
                spec.entity_name,
            )
            return []

        template_id = self._ensure_template(spec, active_name, templates)

        if active_name in observed:
            self._maybe_update(observed[active_name], spec, template_id)
        else:
            self._create(spec, active_name, entity_id, create_params, template_id)

        if not spec.runner_config.has_config():
            # Runner options were cleared (or the system template is
            # unavailable): the scaleset has been reverted to the default
            # template above, so drop any now-unreferenced custom template.
            self._delete_custom_template(active_name, templates)

        return self._retire_replaced(spec, active_name, observed, templates, family)

    def _retire_replaced(
        self,
        spec: ScalesetSpec,
        active_name: str,
        observed: dict[str, ScaleSet],
        templates: dict[str, Template],
        family: list[str],
    ) -> list[ScalesetProgress]:
        """Hand routing over to the current generation and drain the ones it replaced.

        Workloads route by label, not by scaleset name, and GitHub only assigns jobs to
        a scaleset holding a live listener session. So the replacement is brought up
        first and only then is the old one disabled, which closes its session and leaves
        the replacement as the sole holder of the labels they share. Any label carried by
        both is served throughout — by one scaleset or the other, both fully functional —
        so the changeover has no queue gap, and runners already mid-job are left to
        finish rather than being killed.

        Args:
            spec: The desired scaleset.
            active_name: The generation that should serve *spec*.
            observed: Observed scalesets keyed by name.
            templates: Observed templates keyed by name.
            family: Every live generation of this spec, plus its target name.

        Returns:
            One entry per replaced generation not yet gone.
        """
        # Close the old session only once the replacement exists: disabling any
        # earlier leaves the labels unserved if the charm dies in between.
        replacement_live = active_name in observed and observed[active_name].enabled is True

        progress: list[ScalesetProgress] = []
        for name in family:
            old = observed.get(name)
            if name == active_name or old is None:
                continue
            if not replacement_live:
                progress.append(
                    ScalesetProgress(spec.name, name, active_name, 0, Handover.PENDING)
                )
                continue
            # Truthy, not `is not False`: GARM tags Enabled `omitempty`, so a disabled
            # scaleset comes back with no `enabled` key at all and the client reads None.
            if old.enabled:
                if not self._retire(old):
                    # It is still enabled, so its session is still open and nothing is
                    # draining: report the stalled hand-over rather than a runner count,
                    # which would read as a changeover that is quietly making progress.
                    progress.append(
                        ScalesetProgress(spec.name, name, active_name, 0, Handover.FAILED)
                    )
                    continue
                progress.append(
                    ScalesetProgress(spec.name, name, active_name, self._remaining_runners(old))
                )
                continue
            remaining = self._remaining_runners(old)
            if remaining and not _drain_deadline_passed(old):
                progress.append(ScalesetProgress(spec.name, name, active_name, remaining))
                continue
            if remaining:
                logger.warning(
                    "Scaleset %s still reports %d runner(s) after %s of draining;"
                    " attempting deletion anyway. GARM rejects the delete while runners"
                    " are genuinely active, so no in-flight job is cut short.",
                    name,
                    remaining,
                    DRAIN_DEADLINE,
                )
            if not self._delete_drained(old, templates):
                # Keep reporting it: a scaleset GARM refused to delete is still on
                # GitHub, so the replacement has not actually converged yet.
                progress.append(ScalesetProgress(spec.name, name, active_name, remaining))
        return progress

    def _retire(self, scaleset: ScaleSet) -> bool:
        """Disable a replaced scaleset and stop it launching runners.

        Disabling closes its listener session, handing the shared labels to the
        replacement. GARM's handleScaleDown then reaps idle runners but skips
        RunnerActive, so a runner mid-job finishes instead of being killed. The
        second call is defensive: GARM rejects max_runners=0 on create only.

        Args:
            scaleset: The replaced scaleset.

        Returns:
            Whether the scaleset is now disabled. False leaves both generations
            enabled and their min_idle_runners doubled, so the caller must report the
            changeover as stalled rather than as a drain in progress.

        Raises:
            GarmConnectionError: If GARM is unreachable — see ``_remaining_runners``.
        """
        if scaleset.id is None:
            logger.warning("Scaleset %s has no id; cannot retire it", scaleset.name)
            return False
        logger.info("Retiring replaced scaleset %s (id=%s)", scaleset.name, scaleset.id)
        try:
            self._client.update_scaleset(
                scaleset.id,
                UpdateScaleSetParams(enabled=False, min_idle_runners=0, max_runners=0),
            )
            return True
        except GarmConnectionError:
            raise
        except GarmApiError as exc:
            logger.warning(
                "Could not zero runner counts on scaleset %s; disabling only: %s",
                scaleset.name,
                exc,
            )
        try:
            self._client.update_scaleset(
                scaleset.id, UpdateScaleSetParams(enabled=False, min_idle_runners=0)
            )
        except GarmConnectionError:
            raise
        except GarmApiError as exc:
            logger.warning(
                "Could not disable scaleset %s (will retry on next reconcile): %s",
                scaleset.name,
                exc,
            )
            return False
        return True

    def _remaining_runners(self, scaleset: ScaleSet) -> int:
        """Return how many runners a scaleset still has.

        Args:
            scaleset: The scaleset to inspect.

        Returns:
            The instance count, or 1 when it cannot be read — an unknown count must
            never be mistaken for a drained scaleset and delete live runners.

        Raises:
            GarmConnectionError: If GARM is unreachable. Contained failures are
                per-scaleset; an outage is not, and must reach the charm's status
                rather than be reported as drain progress.
        """
        if scaleset.id is None:
            return 0
        try:
            return len(self._client.list_scaleset_instances(scaleset.id))
        except GarmConnectionError:
            raise
        except GarmApiError as exc:
            logger.warning(
                "Could not count runners of scaleset %s; assuming still draining: %s",
                scaleset.name,
                exc,
            )
            return 1

    def _delete_drained(self, scaleset: ScaleSet, templates: dict[str, Template]) -> bool:
        """Delete a replaced scaleset that has finished draining, and its template.

        Args:
            scaleset: The drained scaleset.
            templates: Observed templates keyed by name.

        Returns:
            Whether the caller can stop tracking it. False means GARM still holds the
            scaleset, so the replacement has not converged yet. An id-less scaleset is
            untouchable rather than gone, but reporting it forever would wedge the
            status, so it reads as done — matching ``_remaining_runners``.

        Raises:
            GarmConnectionError: If GARM is unreachable — see ``_remaining_runners``.
        """
        if scaleset.id is None:
            return True
        logger.info("Deleting drained scaleset %s (id=%s)", scaleset.name, scaleset.id)
        try:
            self._client.delete_scaleset(scaleset.id)
        except GarmConnectionError:
            raise
        except GarmApiError as exc:
            logger.warning(
                "Could not delete drained scaleset %s (will retry on next reconcile): %s",
                scaleset.name,
                exc,
            )
            return False
        self._delete_custom_template(scaleset.name or "", templates)
        return True

    def _delete_orphaned(self, scaleset: ScaleSet) -> bool:
        """Disable then delete a scaleset that is no longer in the desired set.

        Args:
            scaleset: The orphaned scaleset.

        Returns:
            Whether GARM no longer holds it, and so whether its runner template can go
            too. A template is only ever deleted after the scaleset referencing it, so
            a scaleset awaiting a retry keeps the runner config that retry relies on.

        Raises:
            GarmConnectionError: If GARM is unreachable — an outage is not a per-scaleset
                failure and must reach the charm's status rather than read as a sweep
                that found nothing left to do.
        """
        name = scaleset.name or ""
        logger.info("Deleting orphaned scaleset %s (id=%s)", name, scaleset.id)
        if scaleset.id is None:
            logger.warning("Scaleset %s has no id; skipping delete", name)
            return False
        try:
            # Disable the scaleset first so GARM stops launching new runners.
            # GARM returns 400 if the scaleset still has active runners,
            # so disabling first drains it for the next reconcile to clean up.
            self._client.update_scaleset(
                scaleset.id, UpdateScaleSetParams(enabled=False, min_idle_runners=0)
            )
        except GarmConnectionError:
            raise
        except GarmApiError as exc:
            logger.warning("Could not disable scaleset %s before delete: %s", name, exc)
        try:
            self._client.delete_scaleset(scaleset.id)
        except GarmConnectionError:
            raise
        except GarmApiError as exc:
            # 400 means runners are still present; scaleset will be deleted
            # on the next reconcile pass once GARM has cleaned them up.
            logger.warning(
                "Could not delete scaleset %s (runners may still be active; "
                "will retry on next reconcile): %s",
                name,
                exc,
            )
            return False
        return True

    def _resolve_entity_id(self, spec: ScalesetSpec) -> str | None:
        """Return the GARM entity UUID for *spec*, or None if not yet registered."""
        if spec.entity_type == "organization":
            return self._client.find_org_id(spec.entity_name)
        if spec.entity_type == "repository":
            return self._client.find_repo_id(spec.entity_name)
        logger.warning("Unknown entity_type %r for scaleset %s", spec.entity_type, spec.name)
        return None

    def _ensure_template(
        self, spec: ScalesetSpec, scaleset_name: str, templates: dict[str, Template]
    ) -> int:
        """Ensure the scaleset's runner template reflects its runner options.

        Copies the system ``github_linux`` template, injects the runner options,
        and creates or updates the per-scaleset template. The template content is
        refreshed in place (same id) on every reconcile, so an option change is
        applied without touching the scaleset itself.

        Args:
            spec: The desired scaleset.
            scaleset_name: The live name of the scaleset the template belongs to. Each
                generation owns its own template, so a draining predecessor keeps the
                template its runners were built from until it is deleted.
            templates: Observed templates keyed by name.

        Returns:
            The custom template id to reference from the scaleset, or ``0`` to use
            GARM's default template (no runner options set, or the system template
            is unavailable and no custom template already exists). Returning ``0``
            for a scaleset that previously had a custom template detaches it.
        """
        custom_name = f"{SYSTEM_TEMPLATE_NAME}-{scaleset_name}"
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
                    scaleset_name,
                )
                return existing.id or 0
            logger.warning(
                "System template %s not found; scaleset %s will use the default template",
                SYSTEM_TEMPLATE_NAME,
                scaleset_name,
            )
            return 0

        new_data = build_template_data(self._template_bytes(base), spec.runner_config)
        if existing is not None:
            if existing.id is None:
                logger.warning(
                    "Runner template %s has no id; scaleset %s will use the default template",
                    custom_name,
                    scaleset_name,
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
            description=f"Runner template for scaleset {scaleset_name}",
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
    def _to_create_params(spec: ScalesetSpec, scaleset_name: str) -> CreateScaleSetParams:
        """Build and validate CreateScaleSetParams from a ScalesetSpec.

        Args:
            spec: The desired scaleset specification.
            scaleset_name: The live name to create the scaleset under.

        Returns:
            Validated CreateScaleSetParams ready for the GARM API.

        Raises:
            ValidationError: If the spec data fails Pydantic model validation.
        """
        return CreateScaleSetParams.model_validate(
            {
                "name": scaleset_name,
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
        scaleset_name: str,
        entity_id: str,
        params: CreateScaleSetParams,
        template_id: int,
    ) -> None:
        if template_id:
            params.template_id = template_id
        logger.info("Creating scaleset %s under %s %s", scaleset_name, spec.entity_type, entity_id)
        if spec.entity_type == "organization":
            self._client.create_org_scaleset(entity_id, params)
        else:
            self._client.create_repo_scaleset(entity_id, params)

    def _maybe_update(self, observed: ScaleSet, spec: ScalesetSpec, template_id: int) -> None:
        observed_labels = _observed_labels(observed)
        if observed_labels != sorted(spec.labels):
            logger.warning(
                "Scaleset %s carries labels %s but %s were expected; updating its other"
                " fields anyway. Labels are immutable in GitHub — delete this scaleset"
                " in GARM to let the charm recreate it with the expected labels.",
                observed.name,
                observed_labels,
                sorted(spec.labels),
            )

        observed_template_id = observed.template_id or 0

        # _needs_update already covers the template id (its last clause), so an
        # id change alone forces an update here.
        if not self._needs_update(observed, spec, template_id):
            logger.debug("Scaleset %s is up to date", observed.name)
            return

        # UpdateScaleSetParams omits None fields (exclude_none), so None can only
        # leave extra_specs untouched, never clear them. Send an explicit empty
        # dict when the desired extra specs are empty but the scaleset still carries
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
        logger.info("Updating scaleset %s (id=%s)", observed.name, observed.id)
        if observed.id is None:
            logger.warning("Scaleset %s has no id; skipping update", observed.name)
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
