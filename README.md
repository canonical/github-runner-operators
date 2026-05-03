# GitHub runner operators

This repository contains applications, Juju charms, Grafana dashboards and actions related to operating and using
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

## Charms

- **planner-operator** (`charms/planner-operator/`): tells the GitHub runner
  charm how many runners of each type to deploy, based on incoming workflow
  job events.
- **webhook-gateway-operator** (`charms/webhook-gateway-operator/`): receives
  GitHub webhooks and forwards workflow job events to a message broker for the
  planner to consume.

## Documentation

Our documentation is stored in the `docs` directory.
It is based on the Canonical starter pack
and hosted on [Read the Docs](https://documentation.ubuntu.com/github-runner-operators/latest/).
In structuring, the documentation employs the [Diátaxis](https://diataxis.fr/) approach.

You may open a pull request with your documentation changes, or you can
[file a bug](https://github.com/canonical/github-runner-operators/issues) to provide constructive feedback or suggestions.

To run the documentation locally before submitting your changes:

```bash
cd docs
make run
```

GitHub runs automatic checks on the documentation
to verify spelling, validate links and style guide compliance.

You can (and should) run the same checks locally:

```bash
make spelling
make linkcheck
make vale
make lint-md
```
