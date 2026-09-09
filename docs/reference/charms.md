# Charms

This page describes the GARM and GARM configurator charms. The relevant information for a minimal deployment is provided here.

## GARM charm

The GARM charm deploys and manages the [GARM](https://github.com/cloudbase/garm) service for managing GitHub self-hosted
runners.

### Actions

There is no mandatory action for GARM charm to function.

See [Actions for GARM charm](https://charmhub.io/garm/actions).

### Configurations

The credentials to access GitHub API are required for GARM charm to function. The GARM charm currently supports only 
GitHub App authentication. See `app-secret-key` and `app-secret-key-id` configurations for more details.

See [Configurations for GARM charm](https://charmhub.io/garm/configurations).

### Integrations

The GARM charm must be integrated with a PostgreSQL charm, and at least one GARM configurator charm.
The PostgreSQL charm is for storing runner and job states, while GARM configurator charms provider the configuration for
a single set GitHub self-hosted runners.

The GARM charm supports integration with COS (Canonical Observability Stack). See [observe your charm with COS lite](https://canonical.com/juju/docs/ops/latest/tutorial/from-zero-to-hero-write-your-first-kubernetes-charm/observe-your-charm-with-cos-lite/).

See [Integrations for GARM charm](https://charmhub.io/garm/integrations).

## GARM configurator charm

The GARM configurator charm is for provider a set of configurations of GitHub runner scaleset to the GARM charm. Multiple GARM configurator charms can be integrated to a single GARM charm. With each instance of GARM configurator charm representing a single GitHub runner scaleset in GARM.

Currently, the GARM charm and GARM configurator charm only support the [GARM OpenStack provider](https://github.com/cloudbase/garm-provider-openstack).

### Actions

The GARM configurator charm has no actions.

### Configurations

The GARM configurator charm has all the relevant configuration for the GARM scaleset. The `architecture` configuration to specify the CPU architecture of the runner is mandatory. The OpenStack credentials are required for the GARM OpenStack provider to function. See `openstack-auth-url`, `openstack-password`, `openstack-project-domain-name`, `openstack-project-name`, `openstack-user-domain-name`, `openstack-user-name`.

While the rest of the configurations are optional or have reasonable defaults. It is recommended to review all the configurations for this charm.

See [Configurations for GARM configurator charm](https://charmhub.io/garm-configurator/configurations).

### Integrations

The GARM configurator charm needs to be integrated with a GARM charm and a 
[GitHub image builder charm](https://charmhub.io/github-runner-image-builder).
The GARM charm manages the GitHub self-hosted runners according to the configuration on the GARM configurator charm.
The GitHub image builder charm is for building images for the GitHub self-hosted runners.

See [Integrations for GARM configurator charm](https://charmhub.io/garm-configurator/integrations).
