# GitHub runner operators

GitHub runner operators are a set of Juju charms that operate self-hosted GitHub Actions runners.
The product receives GitHub webhooks, routes job events through a message broker, and exposes a
planner API that coordinates runner capacity and job lifecycle data.

## What it is

This repository ships two primary charms:

- GitHub runner webhook gateway: a web service that validates GitHub webhook signatures and forwards workflow job events to an AMQP-compatible message broker.
- GitHub runner planner: a REST API service that consumes workflow job events, records job state in PostgreSQL, and manages runner flavors and auth tokens for downstream runner integrations.

## Who it is for

This product is intended for platform engineers, SREs, and GitHub organization administrators who
need reliable, observable, and policy-driven control of self-hosted runners at scale.

## Core dependencies and integrations

- AMQP message broker: required by both charms for moving webhook events from the gateway to the planner. RabbitMQ is the expected broker.
- PostgreSQL: required by the planner to persist job and flavor data.
- Tracing and metrics: both charms can emit OpenTelemetry data and Prometheus metrics so that Grafana dashboards and tracing backends can be used for observability.
- GitHub runner charm: consumes the planner relation to retrieve auth tokens and desired flavor configuration.

## How the pieces fit

GitHub sends workflow job webhooks to the webhook gateway. The gateway validates and forwards
events to the broker. The planner consumes those events, stores job state, and exposes APIs and
relations that allow the GitHub runner charm to provision the right runners for each job.

## Contents

1. [Reference](reference)
   1. [Architecture](reference/architecture.md)
   2. [Charms](reference/charms.md)
