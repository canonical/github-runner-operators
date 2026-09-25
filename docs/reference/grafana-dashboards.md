# Grafana dashboards

## Dashboard directories

| Directory | Purpose |
|---|---|
| `charms/<charm>/cos_custom/grafana_dashboards/` | Dashboards for a specific charm's workload metrics |
| `charms/garm/cos_custom/grafana_dashboards/` | GARM controller and runner operations metrics |
| `runner_grafana_dashboards/` | Dashboards for runner VM host-level metrics (CPU, memory, disk, network) |

## Conventions

Dashboard JSON files should use `__inputs` to declare the data source (type `prometheus`).
Setting `"editable": false` is recommended for clarity. Metric names follow the
[OpenTelemetry host metrics receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver)
Prometheus naming convention (for example, `system_cpu_time_seconds_total`).

## GARM dashboard set

The GARM dashboards are delivered to COS Grafana through the `grafana-dashboard`
relation. They use the `prometheusds` input and share Juju topology filters.

| Dashboard | Focus |
|---|---|
| `garm_operations.json` | Fleet health, CI queue latency, capacity, and controller signals |
| `garm_jobs.json` | Queue and execution latency, job outcomes, and service-level objectives |
| `garm_pools_scalesets.json` | Pool capacity, scale-set demand, listener state, and lifecycle failures |
| `garm_control_plane.json` | GitHub API, provider, webhook, watcher, and build diagnostics |

GARM alert rules are stored under `charms/garm/src/prometheus_alert_rules/` and
are forwarded to COS Prometheus by the charm's metrics endpoint relation. The
initial thresholds are operational defaults and should be tuned to production
baselines.
