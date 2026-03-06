# Charms

This product is composed of two primary charms. The sections below describe each charm, its role,
and the integrations it expects in a typical deployment.

## GitHub runner webhook gateway charm

Purpose

- Receives GitHub webhooks and validates the `X-Hub-Signature-256` HMAC signature.
- Forwards workflow job events and GitHub request metadata to an AMQP-compatible message broker.

Required integrations

- AMQP message broker: the charm requires a `rabbitmq` relation to push webhook events.

Optional integrations

- Tracing: the charm supports optional `tracing` relation to export OpenTelemetry traces.”

Configuration

- Webhook secret: required to validate GitHub webhook signatures.

## GitHub runner planner charm

Purpose

- Provides a REST API for job and flavor management.
- Consumes workflow job events from the AMQP broker and persists state in PostgreSQL.
- Issues and reconciles auth tokens and flavor definitions for runner integrations.

Required integrations

- AMQP message broker: the charm requires a `rabbitmq` relation to consume webhook events.
- PostgreSQL: the charm requires a `postgresql` relation to store job and flavor data.

Optional integrations

- Tracing: the charm can export OpenTelemetry traces when connected to a tracing charm.

Provided integrations

- Planner relation: the charm provides the `planner` relation endpoint (interface `github_runner_planner_v0`) so the GitHub runner charm can
  retrieve auth tokens and desired flavor state.

Configuration

- `admin-token`: required to create or delete general auth tokens.
