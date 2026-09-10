---
title: ADR-003 - scale set label changes by replacement
author: Andrew Liaw (andrew.liaw@canonical.com)
date: 2026/08/14
domain: architecture
replaced-by:
---

# Scale set label changes by replacement

GitHub assigns a scale set's labels at creation and provides no API to change them.
The GARM charm applies a label change by creating a replacement scale set and draining its predecessor, deriving both names from a hash of their labels.

## Context

`UpdateScaleSetParams` exposes no labels field.
A drain lasts as long as its longest in-flight job. These are self-hosted runners, so the limit is GitHub's five-day self-hosted job cap, not the six hours a GitHub-hosted runner gets — either way exceeding any hook's execution budget.

## Decision

A live scale set is named `<configured name>-<first 8 characters of the SHA-256 digest of its sorted labels>`.
Only labels feed the digest; all other fields are updated in place.

Each reconcile advances the changeover by one step:

1. Create the replacement under its label-hashed name. The predecessor remains enabled.
2. When the replacement is observed enabled, set the predecessor to `enabled=false`, `min_idle_runners=0`, `max_runners=0`.
3. While the predecessor reports runners, report progress and take no action.
4. When it reports no runners, delete it and its runner template.

Disabling closes the predecessor's listener session: `listener.Stop()` calls `DeleteMessageSession`, so the session is deleted GitHub-side rather than dropped locally, and `keepListenerAlive` does not restart it while the scale set is disabled.
Labels common to both generations are served by one scale set or the other for the duration, subject to the open question recorded below.
The charm reports an active status naming the configured scale set and its phase, and drops the phase from the status once the predecessor is deleted.

The design depends on five behaviors, verified against the GitHub API and the GARM source:

- GitHub enforces uniqueness on `name` within a runner group. A duplicate name returns `400 RunnerScaleSetExistsException`; overlapping and identical label sets under distinct names return `200`.
- `handleScaleDown` skips instances whose `RunnerStatus` is `RunnerActive` or `RunnerTerminated`, so an instance executing a job is not removed. `handleScaleUp` returns when `Enabled` is false.
- `handleAutoScale` runs on a five-second ticker and is not gated on `Enabled`. `handleScaleSetUpdateOperation` retains the worker; only `handleScaleSetDeleteOperation` stops it. Disabling stops the listener alone.
- `targetRunners` evaluates `min(MinIdleRunners + DesiredRunnerCount, MaxRunners)`, which is 0 when `max_runners` is 0. `UpdateScaleSetByID` validates only `min_idle_runners <= max_runners`; the `max_runners != 0` constraint applies to `CreateScaleSetParams.Validate` alone.
- Nothing writes the `scale_sets` row while a disabled scale set drains, so its `updated_at` is the moment it was disabled — which is what the drain deadline below measures from. The only writes to that row outside an API update are `SetScaleSetLastMessageID` and `SetScaleSetDesiredRunnerCount`, both called from the listener's message handler, and the listener is stopped. `handleAutoScale` keeps running but writes instances, a separate table.

One behavior is not established by either source.
Deleting the message session stops GARM receiving job assignments; whether GitHub stops assigning jobs to a scale set that still exists with the same labels in the same runner group is undocumented, and the GARM source cannot answer it.
If GitHub does continue to assign, a job routed to the predecessor after the disable is not delivered, because GARM does not reopen the session to resume from `last_message_id`; the job waits until the predecessor is deleted, bounded by the drain deadline below.
Both generations carry the shared labels for the whole drain, so this would not be a rare case.
Confirming it requires an observed run rather than a source reference.

## Alternatives considered

Deleting and recreating the scale set under one name was rejected: it terminates in-flight jobs and leaves an interval in which no scale set carries the labels.

A monotonic suffix such as `-v1` and `-v2` was rejected: deriving the next suffix requires the current one, reintroducing persisted state.
A digest also maps a reverted label set back onto the name that generation already holds, so a draining predecessor is re-adopted rather than a third scale set created.

Recording the changeover in peer relation data or on disk was rejected: it establishes a second source of truth alongside GARM and requires its own cleanup.

Blocking the hook until the drain completes was rejected: the drain can exceed five days.

## Consequences

Live names carry a hash suffix, so `garm-cli scaleset list` reports `my-scaleset-1a2b3c4d`.
The configured name remains the operator-facing identity and is what the unit status reports.
Names are capped at 64 characters; a longer configured name is truncated and suffixed with a digest of its full value, so names sharing a prefix resolve to distinct scale sets.
The cap is the charm's own conservative bound on the System label GitHub registers the scale set under: GARM validates only that the name is non-empty.
It could not have been this generous before the GARM bump recorded in the changelog for 2026-09-04 — GARM built the OpenStack `garm-pool-id` instance tag from the scale set name, so a name over 10 characters overran Nova's 60-character tag limit and failed every instance creation.
GARM now derives that tag from a fixed-length UUID, so the name no longer feeds it.

Moving the live name is a breaking change for workflows that route by it.
GARM registers the scale set name as a GitHub `System` label alongside the configured ones, so a job with `runs-on: <configured name>` was assigned to it before this change and is not after: the label is now `<configured name>-<label hash>`, and it changes again on every label change.
There is no stable name-derived label to route by, so jobs must use a configured label instead.
The tutorial documented `runs-on: tutorial-scaleset` and is updated accordingly.
Adding the configured name to the label set would restore it, at the cost of a label the operator did not ask for; it was left out rather than decided implicitly here.

A changeover spans three reconciles, so at the default update-status interval a label change with no in-flight jobs completes in approximately 15 minutes.
The unit stays active throughout, carrying the phase as its status message.
Maintenance was rejected: the service is fully functional for the whole drain, and a drain reaching the deadline below would otherwise block `juju wait-for` and integration tests on hours of healthy background convergence.

The blue/green sequence covers label changes, not the first upgrade onto this scheme.
A scale set created before it carries the un-suffixed name, which is not a generation of anything, so the first reconcile creates the replacement and hands the predecessor to the orphan sweep in the same pass — disabling it, removing its runners, and deleting it once GARM reports none left.
The predecessor's listener session therefore closes before the replacement is confirmed live, which is the queue gap the design otherwise avoids, and `reconcile` reports no changeover so the unit stays plainly active throughout.
A runner mid-job is still left alone and removed on a later pass, so no in-flight job is cut short.
Adopting the un-suffixed scale set in place was implemented and then removed: it was the only place the live name depended on observed GARM state rather than being a pure function of the spec, and the deployment it protected is edge-only.

Both generations carry the full `min_idle_runners` until the predecessor is deleted, so the idle runner count doubles for the duration of the drain.
Against a fixed OpenStack quota the replacement may be unable to spawn runners at all, which stalls the changeover it is meant to complete.
Operators should size the quota for twice the configured idle count.

Each generation owns a runner template named after its live scale set, so a draining predecessor retains the template its runners were built from.

GARM rejects a scale set delete while it still lists any instance, not only an active one, so an instance GARM's own reaper never clears would block deletion indefinitely.
Past the drain deadline the charm stops waiting on that reaper and removes what remains directly — the same guarded cleanup the orphan sweep uses: a plain delete for anything removable, escalating to forced removal only once GARM itself is stuck carrying one out, and leaving a genuinely running job's runner alone.
The scale set is deleted once none remain.

A runner GARM will not accept a delete for at all is the one case the charm cannot resolve.
`DeleteRunner` validates the runner's status before it reads `forceDelete`, so a forced delete is refused for exactly the statuses a plain one is, and the scale set cannot be deleted while the runner is listed.
Past the drain deadline the charm reports that runner at error level and keeps retrying, rather than logging a "will retry" line that has stopped being true: only GARM moving the runner on, or an operator clearing it, ends that state.

The 32-bit digest can collide, leaving a scale set whose labels do not match its spec.
The charm logs both label sets and applies the remaining fields, rather than blocking updates to image, flavor, and runner counts while the mismatch persists.
