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

The planner charm stores the runner-managed flavor name in the existing Juju secret labeled by relation ID (`relation-{id}`), alongside the auth token.
The secret content includes:
- `token`
- `managed-flavor`

During active relation reconciliation:
1. The charm ensures relation auth token/secret exists.
2. If relation flavor is present, it ensures flavor exists via planner API `POST /api/v1/flavors/{name}` (idempotent via conflict handling) using relation-provided flavor config.
3. It writes flavor name to `managed-flavor` in the relation secret.
4. If relation flavor is unset, it removes `managed-flavor` from the secret to avoid stale cleanup.

During orphan cleanup:
1. The charm reads `managed-flavor` from the secret.
2. If present, it calls planner API `DELETE /api/v1/flavors/{name}`.
3. If flavor deletion succeeds, it removes the secret and deletes the auth token.
4. If flavor deletion fails, the hook errors and Juju retries with the same secret/token state.

Active relations and orphaned tokens are determined holistically from current relation state during reconciliation, without relying on relation event deltas.

## Alternatives considered

Other places to store flavor cleanup state include peer relation data or local files.
These add extra charm state management and do not improve cleanup reliability.

Another alternative is split ownership where github-runner creates flavors and planner only deletes them.
This was rejected because split ownership duplicates API coupling and weakens holistic reconciliation.

Another alternative is encoding the relation ID in the flavor name (e.g., `relation-{id}-{flavor_name}`) so that managed flavors can be discovered by listing flavors and filtering by prefix.
This was rejected because the flavor name appears in Grafana dashboards, Prometheus metrics labels, and other observability surfaces, where the relation ID prefix would add noise with no operational value.

Another alternative is event-specific cleanup only in `relation_broken`.
This conflicts with the holistic reconciliation approach and is less resilient to event ordering/retries.

## Consequences

The change reuses existing Juju secret infrastructure and avoids Go-side API changes.
The github-runner charm only needs to publish desired flavor state in relation data and does not need a planner API client for flavor management.
The relation secret gets an additional revision when flavor data is learned or updated.
Cleanup remains idempotent because planner flavor deletion is idempotent.
