# GitHub runner operators

This repository contains applications, juju charms, Grafana dashboards and actions related to operating and using
self-hosted GitHub Actions runners.


## Repository layout

```
actions/
  enable-log-forwarding/    # GitHub Action: enable log forwarding on runners

charms/
  planner-operator/         # Juju charm: GitHub runner planner
    cos_custom/
      grafana_dashboards/   # Grafana dashboards for the planner charm
  webhook-gateway-operator/ # Juju charm: GitHub webhook gateway

cmd/
  planner/                  # Application entry point: planner
  webhook-gateway/          # Application entry point: webhook gateway

internal/                   # Shared Go packages

docs/                       # Documentation

runner_grafana_dashboards/  # Grafana dashboards for runner VM host metrics
```

## Further information

Further information can be found in the `docs/` directory.
