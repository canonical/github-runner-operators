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

(garm-charm-security-groups)=

### Security groups

When a configurator publishes `security-group-rules`, the GARM charm creates one OpenStack
security group for each scale set, named `garm-<scale set name>`, in that configurator's project.
It keeps the group's rules equal to the published list — a rule that is not listed is removed,
including one added by hand — and passes the group's id to the OpenStack provider as the scale
set's `security_groups` extra spec, so every runner of that scale set is attached to it.

The GARM charm owns the group's lifecycle because it is the charm that knows when the group can
go. A group is deleted once no scale set claims it: when a scale set is renamed or removed, its
runners are drained and deleted first, then the group follows. A group that a port still
attaches cannot be deleted; that is expected for some time after a scale set is removed, because
OpenStack removes the port asynchronously, so it is logged and retried on the next reconcile.

Two limits are worth knowing. Runners that already exist keep the group they were launched with,
so a scale set picks up a new or changed group only as its runners are replaced. And removing
only the configurator takes its credentials with it, so the GARM charm cannot delete the
remaining groups; remove the GARM application too.

Scale set names must be unique within a project: the group is named after the scale set, so two
deployments using the same name would share one group and keep removing each other's rules.

The OpenStack credentials need `create_security_group`, `delete_security_group`,
`create_security_group_rule`, and `delete_security_group_rule`, plus read access to security
groups and their rules, which the default `reader` role provides. Credentials that may not delete
groups still work: the charm logs a warning and keeps the groups it cannot remove.

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

The `security-group-rules` option, on by default, describes the OpenStack security group each
scale set's runners should be attached to. The configurator validates the rules and publishes
them on the `garm-configurator` relation; it makes no OpenStack call itself, so it needs no
permissions and no network path to the cloud. The GARM charm creates and maintains the group
(see [security groups in the GARM charm](#garm-charm-security-groups)).

Each rule takes a `direction` (`ingress` or `egress`), an optional `protocol` (`tcp`, `udp`,
`icmp`, `icmpv6`, or `any`), optional `port_min`/`port_max` for `tcp` and `udp`, and an optional
`remote_ip_prefix` CIDR. Without a prefix a rule covers every address of its ethertype, which is
IPv4 unless the CIDR is IPv6.

The default allows all egress and no ingress. OpenStack attaches the configured group instead of
the project's default security group, so a list with no egress rule is rejected rather than
converged: a runner with no egress cannot reach GitHub. Nothing the charms provide needs an
ingress rule — the GARM remote shell rides the agent's connection, which the runner opens, and a
`debug-ssh` session is an outbound tmate client on the runner.

Set the option to an empty list to manage no group. The GARM charm then attaches nothing and
removes the group it created, leaving the runners on the project's default group.

A rule change is applied to the group at the next GARM reconcile, which reaches new runners
immediately and existing ones only when they are replaced.

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
