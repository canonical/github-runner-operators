(changelog)=

# Changelog

This changelog documents user-relevant changes across this repository (charms, applications, GitHub Actions, and dashboards).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each revision is versioned by the date of the revision.

## 2026-06-26

- sync GARM GitHub App credentials and endpoints from the garm-configurator relation over the GARM REST API, without restarting the service.

## 2026-06-23

- `waiting-p80-report`: count only jobs we own (those with a non-NULL `assigned_flavor`). Jobs served by runners we don't manage — for example, third-party self-hosted runners on repositories we ingest webhooks from — never match a flavor and were skewing the reported P80. Caveat: for date ranges before the 2026-06-18 case-insensitive label-matching fix, some owned completed jobs were left with a NULL `assigned_flavor` and are likewise excluded, so `sample_count` may be lower than the true total for those older ranges.

## 2026-06-22

- `waiting-p80-report`: clamp negative waiting times (clock skew, `started_at < created_at`) to 0 instead of excluding those jobs. Previously dropping them removed the fastest jobs from the population and biased the reported P80 upward.

## 2026-06-19

- add `waiting-p80-report` standalone CLI that extracts the daily P80 of job waiting time from the planner's PostgreSQL database into a CSV. Not part of the planner charm; no charm or migration change.

## 2026-06-18

- match planner runner labels case-insensitively, so jobs requesting GitHub's implicit label casing (e.g. `X64`, `Linux`) match flavors defined in lowercase. A migration converts existing labels to lowercase and reassigns jobs previously left unmatched due to casing.
- Migrated the RTD documentation URL under the Canonical domain.

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
