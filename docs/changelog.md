(changelog)=

# Changelog

This changelog documents user-relevant changes across this repository (charms, applications, GitHub Actions, and dashboards).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each revision is versioned by the date of the revision.

## 2026-06-08

- Implement the webhook redelivery service.
- reorder the template variables in the GitHub runner VM hostmetrics dashboard.

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
