# GitHub runner operators

This repository contains applications, juju charms, Grafana dashboards and actions related to operating and using
self-hosted GitHub Actions runners.


## Repository layout

```
charms/
  planner-operator/         # Juju charm: GitHub runner planner
    cos_custom/
      grafana_dashboards/   # Grafana dashboards for the planner charm
                            # (served via cos-configuration-k8s, path: charms/planner-operator/cos_custom/grafana_dashboards)
  webhook-gateway-operator/ # Juju charm: GitHub webhook gateway

runner_grafana_dashboards/  # Grafana dashboards for runner VM host metrics
                            # (served via cos-configuration-k8s, path: runner_grafana_dashboards)
```

## Further information

Further information can be found in the `docs/` directory.


## Observability: Grafana dashboards

Dashboards in this repo are delivered to Grafana through
[`cos-configuration-k8s`](https://charmhub.io/cos-configuration-k8s), which syncs
JSON files from this Git repository and provisions them via the `grafana-dashboard`
relation. Provisioned dashboards are **immutable** in Grafana regardless of user
role — they cannot be edited or deleted through the UI.

### Conventions

| Directory | Purpose | `grafana_dashboards_path` config value |
|---|---|---|
| `charms/<charm>/cos_custom/grafana_dashboards/` | Dashboards for a specific charm's workload metrics | `charms/<charm>/cos_custom/grafana_dashboards` |
| `runner_grafana_dashboards/` | Dashboards for runner VM host-level metrics (CPU, memory, disk, network) | `runner_grafana_dashboards` |

Dashboard JSON files should use `__inputs` to declare the datasource (type `prometheus`).
Setting `"editable": false` is recommended for clarity, but is not strictly required:
dashboards delivered through `cos-configuration-k8s` are filesystem-provisioned and
therefore read-only in Grafana regardless of the JSON flag. Metric names follow the
[OpenTelemetry hostmetrics receiver](https://opentelemetry.io/docs/collector/components/#receiver)
Prometheus naming convention (e.g. `system_cpu_time_seconds_total`).
