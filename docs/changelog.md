(changelog)=

# Changelog

This changelog documents user-relevant changes across this repository (charms, applications, GitHub Actions, and dashboards).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Each revision is versioned by the date of the revision.

## 2026-07-12

- `garm`: fix the injected runner-option environment variables so the runner actually reads them. They were written to a file named `env`, but the GitHub Actions runner sources a `.env` file, so the Docker mirror, OpenTelemetry endpoint, job-started hook, and pre-job-script options were silently ignored. They are now written to the `.env` file the runner reads.

## 2026-07-09

- `garm`: apply the Docker registry mirror and runner host preparation on the runner. GARM runs the injected runner-install steps as the unprivileged `runner` user, but the Docker-mirror and host-prep steps ran without `sudo`, so writing `/etc/docker/daemon.json`, restarting Docker, and adding the runner to the `lxd`/`adm` groups all failed silently — the mirror and group membership were never applied. These steps now escalate with `sudo`, matching the rest of the install script.

- `garm`: fix runner provisioning on proxy-only networks. GARM injects a compiled-in wrapper as the cloud-init install script that must reach the GARM API before any runner-template content runs, so the aproxy bootstrap embedded in the template could never bring up egress in time and runners never registered. The aproxy setup is now delivered as a pre-install script (which GARM runs before the wrapper), apt updates are disabled on boot when a proxy is configured, and `snap set aproxy proxy=` now receives a bare `host:port` as aproxy requires.
- `garm`: fix a charm crash when a runner fails to provision. GARM reports the IaaS provider error as a base64 string in the instance's `provider_fault`, but the generated GARM API client expected an integer array and raised a validation error, aborting every reconcile until GARM removed the faulted instance. The client is now pinned to a GARM revision that declares its byte fields as base64 strings (upstream GARM #802), so faulted instances deserialize correctly.

## 2026-07-08

-  Add webhook gateway dashboard panels: three new panels show webhook ingestion, webhook delivery, and webhook redelivery for the webhook gateway. The panels are co-located in the planner dashboard for a better viewing experience, making webhook-related errors such as delivery failures easier to monitor.
-  Fix runner provisioning in the GARM workload: the OpenStack provider binary in the bare-base rock was built dynamically linked, so GARM could not execute it (`fork/exec /usr/local/bin/garm-provider-openstack: no such file or directory`) and no runners were spawned, even though the charm reported `active`. The provider is now built as a fully static, pure-Go binary, matching the GARM binary.
- `garm-configurator`: log the full config-validation detail when configuration is invalid. Juju truncates the blocked unit status to its first line, so a multi-line validation error (for example from an invalid runner option) was not fully visible. The charm now also logs the complete detail at warning level, so it is discoverable in `juju debug-log`.

## 2026-07-06

- `garm`: fix the application status freezing on a stale value. The charm wrote the unit status directly on its own reconcile paths, so the leader's application status was never refreshed and could stay stuck (for example showing `Waiting for pebble ready` while the unit was `active`). Status writes now go through the shared unit/application status helper so both stay in sync.

- `garm-configurator`: reject `max-runner=0` during config validation. GARM rejects scale set creation with `max_runners cannot be 0`, so the charm now surfaces the invalid configuration before publishing unusable scale set data to GARM.

## 2026-07-02

- Fix GARM organization and repository registration: the charm now sets a webhook secret when registering entities. GARM requires a non-empty webhook secret to register an org/repo, so registration previously failed with an opaque server error and scalesets were never created. The charm generates a throwaway secret automatically, so no operator configuration is required.

- Fix TLS verification in the GARM workload: the GARM rock is built on a bare base and previously shipped without a CA trust store, so GARM's statically-linked binary rejected every HTTPS certificate (including GitHub's) with `x509: certificate signed by unknown authority`. The rock now bundles the system CA certificates.

## 2026-06-30

- Register GARM organization and repository entities from the garm-configurator relation over the GARM REST API, binding each to its managed GitHub App credential. Entities are now created before scalesets are reconciled, so scalesets no longer wait indefinitely for an org/repo that nothing registered. Registration is best-effort: if GARM cannot register an entity yet (for example GitHub is briefly unreachable), the charm defers and retries rather than failing the whole sync. Entities that fall out of the relation are deleted once their scalesets have drained.

## 2026-06-29

- Implement the webhook redelivery service.
- route the GARM charm's outbound traffic through the Juju model proxy: model-level `juju-http-proxy`/`juju-https-proxy`/`juju-no-proxy` settings are now applied to GARM and forwarded to the OpenStack provider executable, so OpenStack and GitHub API calls egress via the proxy.

## 2026-06-26

- Sync GARM GitHub App credentials from the garm-configurator relation over the GARM REST API, without restarting the service. Only the built-in `github.com` endpoint is supported.
- `garm-configurator`: add a new required `github-app-id` config option (the numeric GitHub App ID, which GARM uses to authenticate the App) and remove the unused `github-app-client-id` option (GARM authenticates Apps by app ID, not the OAuth client ID). Existing deployments must set `github-app-id`. The `github-app-id` and `github-app-installation-id` options are now integer-typed, so non-numeric values are rejected at config-set time.

## 2026-06-24

- Add debug-ssh relation support for the GARM charm. This allows the GARM charm to be integrated with the tmate-ssh-server charm to enable remote debugging of the runner spawned by the GARM charm.

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
