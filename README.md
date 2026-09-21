# GitHub runner operators

This repository contains applications, Juju charms, Grafana dashboards and actions related to operating and using
self-hosted GitHub Actions runners.


## Repository layout

The Go application code (`cmd/`, `internal/`) follows the
[community Go project layout](https://github.com/golang-standards/project-layout).

```
actions/
  enable-log-forwarding/    # GitHub Action: enable log forwarding on runners

charms/
  garm/                     # Juju charm: GARM
  garm-configurator/        # Juju charm: GARM Configurator
  planner-operator/         # Juju charm: GitHub runner planner
    cos_custom/
      grafana_dashboards/   # Grafana dashboards for the planner charm
  tests/                    # Integration and E2E tests for the charms
  webhook-gateway-operator/ # Juju charm: GitHub webhook gateway

cmd/
  planner/                  # Application entry point: planner
  waiting-p80-report        # Application entry point: tool for calculating p80 waiting time
  webhook-gateway/          # Application entry point: webhook gateway

internal/                   # Shared Go packages

docs/                       # Documentation

runner_grafana_dashboards/  # Grafana dashboards for runner VM host metrics

scripts/                    # Collection of various scripts
```

## Charms

This repository contains four charms, representing two different architectures:

The planner architecture, which is no longer in active development but rather in maintaince mode, is 
implemented by the **planner** and the **webhook-gateway** charms.

The other architecture is based on [GitHub Actions Runner Manager (GARM)](https://github.com/cloudbase/garm) and 
implemented by the **garm** and **garm-configurator** charms.

[Charms](https://canonical.com/juju/docs/github-runner-charms/latest/reference/charms/)
in the documentation for their roles and integrations.

### Charmhub

| Name | Listing |
|------|---------|
| `garm` | https://charmhub.io/garm |
| `garm-configurator` | https://charmhub.io/garm-configurator |
| `github-runner-planner` | https://charmhub.io/github-runner-planner |
| `github-runner-webhook-gateway` | https://charmhub.io/github-runner-webhook-gateway |

## Documentation

Our documentation is stored in the `docs` directory
and can be viewed at https://canonical.com/juju/docs/github-runner-charms/.
It is based on the Canonical Sphinx Stack
and hosted on [Read the Docs](https://about.readthedocs.com/).
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
