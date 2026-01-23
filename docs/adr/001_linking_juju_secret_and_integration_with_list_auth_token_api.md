---
title: ADR-001 - linking Juju secret and integration with list auth token API
author: Andrew Liaw
date: 2026/01/23
domain: architecture
replaced-by: 
---

# Linking Juju secret and integration with list auth token API

In the planner Go application, an API endpoint is added to list the names of all auth tokens.
This API is guarded with admin token level access.

This helps resolve the issue with Juju secret cleanup on integration removed.

## Context

For the planner charm integration with GitHub runner charm, the planner needs to pass a Juju secret containing an auth token to the GitHub runner charm, this is done by creating a Juju secret and passing the Juju secret ID in the integration.
On removing this integration, the Juju secret needs to be cleaned up, which requires the Juju secret ID.

The general way to resolve this is to store the information on which Juju secret is linked to which Juju integration.
The Juju secret can be labelled with a string and retrieved by it.
This allows using a string to link a Juju secret to an integration.

It was decided that the GitHub runner planner charm will be using the [holistic charm pattern](https://discourse.charmhub.io/t/deltas-vs-holistic-charming/11095).
Under the holistic charm pattern, the event handling should not rely on the delta from the events, such as, the integration ID from integration removed event. Therefore, there needs to be a mapping of Juju integration with the Juju secrets.

## Decision

The auth token is named by the integration ID.
On relation removed, the planner checks the list of auth token names and compare it with the integrations.
If there is an auth token without a corresponding integration, then that auth token and the Juju secret with the same label needs to be cleaned up.

## Alternatives considered

Other alternatives include other places to store the state, e.g., peer integration data, local file, etc.
However, since the auth token is already stored in the database, it makes sense to store the state there as well.

## Consequences

### Positive

- The way the Juju secret cleanup is handled fits the holistic charm pattern.
- The API for listing the name of auth token can be used for debugging.

### Negative

- An additional API call to the planner, and database access during each execute of charm events.
- The list auth token API is tied to the cleanup of Juju secrets in the planner charm.
