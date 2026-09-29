# Charm reference

This page describes the two Juju charms that make up the GARM deployment.

## `garm` charm

The `garm` charm deploys and manages GARM on Kubernetes. GARM provides the
API and coordinates GitHub runner scale sets.

### Integrations

Required integrations:

- `postgresql`: provides storage for GARM state.
- `garm-configurator`: provides runner scale set and provider configuration
  through the `garm_configurator_v0` interface.

Optional integrations:

- `debug-ssh`: provides debug SSH access.

### Actions

- `get-credentials`: displays the generated GARM administrator credentials.

### Service endpoints

GARM serves its API and Prometheus metrics on port `8080`.

## `garm-configurator` charm

The `garm-configurator` charm stores the configuration for one GARM runner
scale set and shares it with the `garm` charm.

### Integrations

Required integrations:

- `image`: provides a runner image through the `github_runner_image_v0`
  interface.

Provided integrations:

- `garm-configurator`: provides configuration to the `garm` charm through the
  `garm_configurator_v0` interface.

### Configuration

The configuration options fall into these groups:

- **GitHub:** App ID, installation ID, private key, repository or organization,
  and runner group.
- **OpenStack:** authentication URL, user, password secret, project, domains,
  region, and network.
- **Scale set:** name, flavor, architecture, minimum idle runners, maximum
  runners, and labels.
- **Runner behavior:** shell access, pre-install scripts, Docker registry
  mirror, HTTP proxy, proxy exclusions and redirects, OpenTelemetry endpoint,
  and pre-job script.

The `openstack-password` and `github-app-private-key` options are Juju secret
references. Do not provide those credentials as plain-text configuration.
