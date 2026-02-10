---
title: ADR-002 - flavor cleanup on relation removal
author: Christopher Bartz (christopher.bartz@canonical.com)
date: 2026/02/10
domain: architecture
replaced-by: 
---

# Flavor cleanup on relation removal

The planner charm currently cleans up auth tokens and Juju secrets when the planner relation is removed.
Flavor cleanup is also required when the relation is removed.

## Context

The GitHub runner charm sets the flavor name in relation app data.
Flavor names are arbitrary and are not safely reconstructable from relation ID.
When relation cleanup runs, the relation app data may no longer be available.

The planner charm follows a [holistic charm pattern](https://discourse.charmhub.io/t/deltas-vs-holistic-charming/11095).
Relation removal cleanup is done by reconciling active relations with planner auth tokens.
This requires persistent state that survives relation removal hooks.

## Decision

The planner charm stores the runner-managed flavor name in the existing Juju secret labeled by relation ID (`relation-{id}`), alongside the auth token.
The secret content includes:
- `token`
- `managed-flavor`

During orphan cleanup:
1. The charm reads `managed-flavor` from the secret.
2. If present, it calls planner API `DELETE /api/v1/flavors/{name}`.
3. If flavor deletion succeeds, it removes the secret and deletes the auth token.
4. If flavor deletion fails, the hook errors and Juju retries with the same secret/token state.

Active relations and orphaned tokens are determined holistically from current relation state during reconciliation, without relying on relation event deltas.

## Alternatives considered

Other places to store flavor cleanup state include peer relation data or local files.
These add extra charm state management and do not improve cleanup reliability.

Another alternative is enforcing flavor naming conventions derived from relation ID.
This is not viable because flavor names are user-defined and managed by the GitHub runner side.

Another alternative is event-specific cleanup only in `relation_broken`.
This conflicts with the holistic reconciliation approach and is less resilient to event ordering/retries.

## Consequences

The change reuses existing Juju secret infrastructure and avoids Go-side API changes.
The relation secret gets an additional revision when flavor data is learned or updated.
Cleanup remains idempotent because planner flavor deletion is idempotent.
