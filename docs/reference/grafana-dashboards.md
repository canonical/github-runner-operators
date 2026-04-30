# Grafana dashboards

## Dashboard directories

| Directory | Purpose |
|---|---|
| `charms/<charm>/cos_custom/grafana_dashboards/` | Dashboards for a specific charm's workload metrics |
| `runner_grafana_dashboards/` | Dashboards for runner VM host-level metrics (CPU, memory, disk, network) |

## Conventions

Dashboard JSON files should use `__inputs` to declare the datasource (type `prometheus`).
Setting `"editable": false` is recommended for clarity. Metric names follow the
[OpenTelemetry hostmetrics receiver](https://opentelemetry.io/docs/collector/components/#receiver)
Prometheus naming convention (for example, `system_cpu_time_seconds_total`).
