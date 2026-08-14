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
A drain lasts as long as its longest in-flight job, up to GitHub's six-hour limit, exceeding any hook's execution budget.

## Decision

A live scale set is named `<configured name>-<first 8 characters of the SHA-256 digest of its sorted labels>`.
Only labels feed the digest; all other fields are updated in place.

Each reconcile advances the changeover by one step:

1. Create the replacement under its label-hashed name. The predecessor remains enabled.
2. When the replacement is observed enabled, set the predecessor to `enabled=false`, `min_idle_runners=0`, `max_runners=0`.
3. While the predecessor reports runners, report progress and take no action.
4. When it reports no runners, delete it and its runner template.

Disabling closes the predecessor's listener session, ending job assignment to it.
Labels common to both generations are served by one scale set or the other for the duration.
The charm reports a maintenance status naming the configured scale set and its phase, and returns to active once the predecessor is deleted.

The design depends on four behaviors, verified against the GitHub API and the GARM source:

- GitHub enforces uniqueness on `name` within a runner group. A duplicate name returns `400 RunnerScaleSetExistsException`; overlapping and identical label sets under distinct names return `200`.
- `handleScaleDown` skips instances whose `RunnerStatus` is `RunnerActive` or `RunnerTerminated`, so an instance executing a job is not removed. `handleScaleUp` returns when `Enabled` is false.
- `handleAutoScale` runs on a five-second ticker and is not gated on `Enabled`. `handleScaleSetUpdateOperation` retains the worker; only `handleScaleSetDeleteOperation` stops it. Disabling stops the listener alone.
- `targetRunners` evaluates `min(MinIdleRunners + DesiredRunnerCount, MaxRunners)`, which is 0 when `max_runners` is 0. `UpdateScaleSetByID` validates only `min_idle_runners <= max_runners`; the `max_runners != 0` constraint applies to `CreateScaleSetParams.Validate` alone.

## Alternatives considered

Deleting and recreating the scale set under one name was rejected: it terminates in-flight jobs and leaves an interval in which no scale set carries the labels.

A monotonic suffix such as `-v1` and `-v2` was rejected: deriving the next suffix requires the current one, reintroducing persisted state.
A digest also maps a reverted label set back onto the name that generation already holds, so a draining predecessor is re-adopted rather than a third scale set created.

Recording the changeover in peer relation data or on disk was rejected: it establishes a second source of truth alongside GARM and requires its own cleanup.

Blocking the hook until the drain completes was rejected: the drain can exceed six hours.

## Consequences

Live names carry a hash suffix, so `garm-cli scaleset list` reports `my-scaleset-1a2b3c4d`.
The configured name remains the operator-facing identity and is what the unit status reports.
Names are capped at 64 characters; a longer configured name is truncated and suffixed with a digest of its full value, so names sharing a prefix resolve to distinct scale sets.

A changeover spans three reconciles, so at the default update-status interval a label change with no in-flight jobs completes in approximately 15 minutes.
The unit reports maintenance throughout, so callers waiting on active status wait for the drain.

Each generation owns a runner template named after its live scale set, so a draining predecessor retains the template its runners were built from.

An instance GARM does not remove would block deletion indefinitely, so after seven hours the charm stops gating on its runner count and attempts deletion on each reconcile.
GARM rejects that request while the scale set has active runners, which bounds the effect.

The 32-bit digest can collide, leaving a scale set whose labels do not match its spec.
The charm logs both label sets and applies the remaining fields, rather than blocking updates to image, flavor, and runner counts while the mismatch persists.
