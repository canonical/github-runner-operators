---
title: ADR-002 - planner-managed flavor lifecycle from relation state
author: Christopher Bartz (christopher.bartz@canonical.com)
date: 2026/02/10
domain: architecture
replaced-by: 
---

# Planner-managed flavor lifecycle from relation state

The planner charm reconciles auth tokens and Juju secrets for the planner relation.
Flavor resources should follow the same ownership and reconciliation model.

## Context

The GitHub runner charm sets flavor state in relation app data.
Flavor names are arbitrary and are not safely reconstructable from relation ID.
When relation cleanup runs, the relation app data may no longer be available.

The planner charm follows a [holistic charm pattern](https://discourse.charmhub.io/t/deltas-vs-holistic-charming/11095).
Relation removal cleanup is done by reconciling active relations with planner auth tokens.
This removal requires a persistent state that survives relation removal hooks.

## Decision

The planner charm owns full lifecycle of relation-managed flavors (create and delete).
GitHub runner declares desired flavor state in relation data, and planner reconciles actual state.

During active relation reconciliation:
1. The charm ensures relation auth token/secret exists.
2. It builds the desired set of flavors from active relation data.
3. It lists current planner flavors via `GET /api/v1/flavors`.
4. It ensures each desired flavor exists with matching config (delete/create when stale, create when missing).
5. It deletes flavors present in planner but absent from desired relation state.

During orphan cleanup:
1. The charm removes the relation secret and deletes the auth token.
2. Flavor cleanup is handled by the flavor reconciliation step, which compares planner DB state with active relations.

Active relations and orphaned tokens are determined holistically from current relation state during reconciliation, without relying on relation event deltas.

## Alternatives considered

Another alternative is encoding the relation ID in the flavor name (e.g., `relation-{id}-{flavor_name}`) so that managed flavors can be discovered by listing flavors and filtering by prefix.
This was rejected because the flavor name appears in Grafana dashboards, Prometheus metrics labels, and other observability surfaces, where the relation ID prefix would add noise with no operational value.

Another alternative is storing the managed flavor name in the per-relation Juju secret (alongside the auth token) and reading it back during cleanup.
This was rejected because it couples reconciliation logic to Juju secret read-modify-write operations and makes the secret a second source of truth alongside the planner database.
The DB-based approach uses a single source of truth and avoids fragile secret content management.

## Consequences

The change depends on planner exposing `GET /api/v1/flavors` so the charm can reconcile DB state holistically.
The github-runner charm only needs to publish desired flavor state in relation data and does not need a planner API client for flavor management.
Cleanup remains idempotent because planner flavor deletion is idempotent.
If two relations declare the same flavor name, one relation's cleanup can temporarily delete a flavor still desired by the other.
The next hook execution recreates it via the remaining relation's reconciliation pass.
