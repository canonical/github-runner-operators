(changelog)=

# Changelog

This changelog documents user-relevant changes across this repository (charms, applications, GitHub Actions, and dashboards).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each revision is versioned by the date of the revision.

## 2026-06-18

- match planner runner labels case-insensitively, so jobs requesting GitHub's implicit label casing (e.g. `X64`, `Linux`) match flavors defined in lowercase. A migration converts existing labels to lowercase and reassigns jobs previously left unmatched due to casing.

## 2026-06-16

- Add Garm configurator relation with GARM charm and write OpenStack provider related toml configurations.

## 2026-06-15

- export GARM Prometheus metrics via the `metrics-endpoint` integration, with JWT authentication disabled on the `/metrics` endpoint. GARM serves its API and metrics on a single fixed port (8080); the framework's `app-port`/`metrics-port`/`metrics-path` options are not used.

## 2026-06-12

- add GARM HTTP API client to the GARM charm: auto-generates admin credentials on first install, calls the GARM `/first-run` endpoint automatically on startup, and stores credentials in a Juju secret (`garm-admin-credentials`).

## 2026-06-08

- reorder the template variables in the GitHub runner VM hostmetrics dashboard.
- add PostgreSQL relation support for persistent storage.

## 2026-06-04

- add GARM Scaleset configurations for the GARM configurator charm.

## 2026-06-03

- update the `includeAll` setting of the `github_runner`, `github_run_id`, and `github_run_attempt` variables for a better dashboard default experience.

## 2026-06-02

- add OpenStack and GitHub creds/configs for the GARM configurator charm.

## 2026-05-25

- add GARM (GitHub Actions Runner Manager) 12-factor charm scaffold with ROCK image, Juju secret management, and TOML config rendering.

## 2026-05-21

Improve the GitHub runner VM hostmetrics dashboard to include the `github_run_id` and `github_run_attempt` attributes.

## 2026-04-22

- add action to allow workflow authors to opt in to forwarding specific log files from self-hosted GitHub runners to Loki through the OpenTelemetry Collector snap.

## 2026-04-13

- add 5xx error logging to planner routes.
