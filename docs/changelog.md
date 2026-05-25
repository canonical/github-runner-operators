(changelog)=

# Changelog

This changelog documents user-relevant changes across this repository (charms, applications, GitHub Actions, and dashboards).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each revision is versioned by the date of the revision.

## 2026-05-25

- add GARM (GitHub Actions Runner Manager) 12-factor charm scaffold with ROCK image, Juju secret management, and TOML config rendering.

## 2026-05-21

Improve the GitHub runner VM hostmetrics dashboard to include the `github_run_id` and `github_run_attempt` attributes.

## 2026-04-22

- add action to allow workflow authors to opt in to forwarding specific log files from self-hosted GitHub runners to Loki through the OpenTelemetry Collector snap.

## 2026-04-13

- add 5xx error logging to planner routes.
