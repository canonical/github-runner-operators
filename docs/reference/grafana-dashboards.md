# Grafana dashboards

## Dashboard directories

| Directory | Purpose |
|---|---|
| `charms/<charm>/cos_custom/grafana_dashboards/` | Dashboards for a specific charm's workload metrics |
| `runner_grafana_dashboards/` | Dashboards for runner VM host-level metrics (CPU, memory, disk, network) |

## Conventions

Dashboard JSON files should use `__inputs` to declare the data source (type `prometheus`).
Setting `"editable": false` is recommended for clarity. Metric names follow the
[OpenTelemetry host metrics receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver)
Prometheus naming convention (for example, `system_cpu_time_seconds_total`).
