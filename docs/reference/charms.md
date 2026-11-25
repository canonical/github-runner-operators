---
myst:
  html_meta:
    "description lang=en": "Reference information for the GARM and garm-configurator Juju charms."
---

(reference_charm_reference)=

# Charms

This page describes the GARM and GARM configurator charms. The relevant information for a minimal deployment is provided here.

## GARM charm

The GARM charm deploys and manages the [GARM](https://github.com/cloudbase/garm) service for managing GitHub self-hosted
runners.

### Actions

There is no mandatory action for GARM charm to function.

```{seealso}
[Actions for GARM charm](https://charmhub.io/garm/actions)
```

### Configurations

The credentials to access the GitHub API are supplied by the GARM configurator through the GARM integration. The
configurator supports GitHub App authentication. See the
[configurations for the GARM configurator charm](https://charmhub.io/garm-configurator/configurations) for details.

```{seealso}
[Configurations for GARM charm](https://charmhub.io/garm/configurations)
```

### Integrations

The GARM charm must be integrated with a PostgreSQL charm, and at least one GARM configurator charm.
The PostgreSQL charm stores runner and job state, while GARM configurator charms provide the configuration for
a single set GitHub self-hosted runners.

The GARM charm supports integration with COS (Canonical Observability Stack). See [observe your charm with COS lite](https://canonical.com/juju/docs/ops/latest/tutorial/from-zero-to-hero-write-your-first-kubernetes-charm/observe-your-charm-with-cos-lite/).

```{seealso}
[Integrations for GARM charm](https://charmhub.io/garm/integrations)
```

## GARM configurator charm

The GARM configurator charm provides a set of configurations of GitHub runner scaleset to the GARM charm. Multiple GARM configurator charms can be integrated to a single GARM charm, with each instance of GARM configurator charm representing a single GitHub runner scaleset in GARM.

Currently, the GARM charm and GARM configurator charm only support the [GARM OpenStack provider](https://github.com/cloudbase/garm-provider-openstack).

### Actions

The GARM configurator charm has no actions.

### Configurations

The GARM configurator charm holds the configuration for one GARM scaleset. The following
options are required because the charm cannot publish a provider configuration or scaleset
without them:

* `name`, `flavor`, and `os-arch`, which identify the scaleset and its runners.
* One of `repo` or `org`, which names the GitHub entity the runners register to.
* An image: either the `image` option or an image published over the image-builder relation.
* The OpenStack credentials required by the provider:
  * `openstack-auth-url`
  * `openstack-network`
  * `openstack-password`
  * `openstack-project-domain-name`
  * `openstack-project-name`
  * `openstack-region-name`
  * `openstack-user-domain-name`
  * `openstack-username`
* The GitHub App ID, installation ID, and private key, which GARM uses to authenticate.

The scaleset options `min-idle-runner`, `max-runner`, `labels`, `runner-group`,
`pre-install-scripts`, `image-visibility`, `security-group`, and the runner networking and
observability options are optional; their documented defaults apply when they are unset.

The charm reports `Blocked` while a required configuration value is missing, or `Waiting`
while the image builder has not yet published an image, and publishes nothing to the GARM
relation. It publishes the complete relation payload only once every required value,
including the image, is available. A relation payload that omits a required
field, or carries a blank value for one, is invalid and the GARM charm blocks rather than
creating a partially configured provider or scaleset.

Review the remaining options and defaults before applying the configuration.

```{seealso}
[Configurations for GARM configurator charm](https://charmhub.io/garm-configurator/configurations)
```

### Integrations

The GARM configurator charm integrates with a GARM charm. The GARM charm manages
GitHub self-hosted runners according to the scaleset configuration published by
the configurator.

```{seealso}
[Integrations for GARM configurator charm](https://charmhub.io/garm-configurator/integrations)
```

## Security

For security-sensitive defaults, trust boundaries, and removal behavior, see the
{ref}`GARM security reference <reference_security>`.
