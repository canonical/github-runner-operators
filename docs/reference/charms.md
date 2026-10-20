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

The GARM configurator charm holds the configuration for one GARM scaleset. The `os-arch` option, which specifies the
runner CPU architecture, is mandatory. The OpenStack credentials required by the provider include:

* `openstack-auth-url`
* `openstack-password`
* `openstack-project-domain-name`
* `openstack-project-name`
* `openstack-user-domain-name`
* `openstack-username`

The GitHub App ID, installation ID, and private key are also required for GitHub authentication. Review the remaining
options and defaults before applying the configuration.

```{seealso}
[Configurations for GARM configurator charm](https://charmhub.io/garm-configurator/configurations)
```

### Security groups

The optional `security-group-rules` option makes the charm manage one OpenStack security group
per scale set. The charm creates the group, named `garm-<name>`, and keeps its rules equal to
the configured list: a rule that is not listed is removed, including one added by hand. The
group's id is published to the GARM charm, which passes it to the OpenStack provider so that
every runner of the scale set is attached to it.

OpenStack attaches the configured groups instead of the project's default security group, so
the rules must allow the runner's outbound traffic to GitHub. When no egress rule is listed the
charm allows all egress for that reason.

A rule change reaches new runners on the next reconcile. A runner that already exists keeps the
group it was launched with until GARM replaces it.

The charm never deletes the group. Clearing the option detaches it from the scale set and
leaves it in place, as does removing the application, so an operator decides when to remove it.

The OpenStack credentials need the `create_security_group`, `create_security_group_rule`, and
`delete_security_group_rule` permissions. The charm does not delete security groups, so it does
not need `delete_security_group`.

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
