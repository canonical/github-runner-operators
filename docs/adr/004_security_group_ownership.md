---
title: ADR-004 - the GARM configurator owns its scale set's OpenStack security group
author: Yangsoo Yoon (yangsoo.yoon@canonical.com)
date: 2026/10/20
domain: architecture
replaced-by:
---

# The GARM configurator owns its scale set's OpenStack security group

`garm-configurator` creates and maintains one OpenStack security group for each scale set it
describes. Creating a resource in a cloud is what Juju calls an
[integrator charm](https://canonical.com/juju/docs/juju-cli/3.6/reference/charm/#integrator-charm),
while this charm is a
[configurator charm](https://canonical.com/juju/docs/juju-cli/3.6/reference/charm/#configurator-charm).
This ADR records why the work belongs there anyway, and what the charm takes on by doing it.

## Context

Juju defines a configurator charm as a workloadless charm that configures another charm once
they are integrated, and an integrator charm as a proxy charm whose non-charmed workload is
cloud functionality. The categories nest: an integrator is a kind of proxy charm, which is a
kind of configurator. What separates them in practice is where the effect lands — another
charm, or an external service.

`garm-configurator` has been the first kind. It holds the definition of one GitHub Actions scale
set, including the OpenStack credentials as Juju secrets, and publishes it over the
`garm-configurator` relation; the `garm` charm consumes it and never writes to the cloud itself.
Managing a security group adds cloud writes to that role: the charm creates `garm-<name>`, keeps
its rules equal to the configured list, publishes the group id for the provider to attach, and
deletes the group when the option is cleared or the application is removed.

The question this ADR answers came from review: should the `garm` charm manage the group
instead, since it owns the scale set's create, drain and delete lifecycle and already receives
the tenant credentials over the relation?

What each side has:

* The configurator holds every input: the tenant credentials, project, region and network, the
  scale set name the group is named after, and the rules.
* The `garm` charm owns the scale set lifecycle, isolates per-scale-set failures in its
  reconciler, and knows data the configurator does not — GARM's own agent URL, and the tmate
  endpoint from the `debug-ssh` relation.

The team rule for this kind of question is written down in the Platform Engineering handbook:
put the logic where the information, the resource's lifecycle, and the credentials already are,
and add relation data when the missing datum lives on the other side
([Configurator and integrator charms](https://github.com/canonical/platform-engineering-docs/blob/main/docs/engineering-practices/charm-development/charm-configurator-and-integrator.md)).

## Decision

The configurator manages the security group.

1. **Every input is already there.** The tenant credentials are the charm's own secret; the
   project, network, scale set name and rules are its configuration. Nothing on the `garm` side
   is needed to create a group that allows all egress and no ingress.
2. **The lifecycle belongs to the definition.** One configurator describes one scale set, and
   the group is scoped to that scale set. Clearing the option, or removing the application,
   deletes the group unless a port still attaches it, so the group does not outlive the
   definition that asked for it.
3. **The credentials stay where they are.** The `garm` charm holds the tenant credentials only
   to render `clouds.yaml` and the provider's TOML for the provider binary; it has no OpenStack
   client. Moving the group there would give it one solely for this.
4. **The relation stays the only transport.** The configurator publishes the group id and the
   `garm` charm passes it to the provider as the scale set's `security_groups` extra spec. The
   `garm` charm still knows nothing about tenant networks or rule syntax.

The cost is that a configurator now performs one integrator job. That is recorded here, in the
charm's reference documentation, and in its changelog, rather than left for an operator to
discover from a blocked unit.

## Consequences

* The configurator now needs network access to Keystone and Neutron, and permissions to create
  and delete security groups and their rules. A deployment whose credentials or network path do
  not allow that blocks until it is given them, or opts out.
* The option is on by default, so a refresh creates one group for each scale set. Groups count
  against the project's security group quota, which defaults to ten.
* A group stays when a port still attaches it, and when the credentials may not delete groups.
  Both cases are logged rather than retried, because neither resolves inside a hook.
* Renaming a scale set leaves the old `garm-<old name>` group behind: the charm keeps no record
  of the previous name, so it cannot know what to delete.
* The unit can block on an OpenStack failure, which it never could before. `update-status` is
  observed so a transient failure retries without waiting for an unrelated event.
* If egress is ever narrowed rather than allowed, the endpoints only the `garm` charm knows —
  the agent URL and the tmate endpoint — must arrive as relation data. That is an addition to
  the relation, not a reason to move the reconcile.

## Alternatives considered

**Manage the group in the `garm` charm.** Raised in review, on the grounds that `garm` owns the
scale set lifecycle and could delete the group after drain, that its reconciler already isolates
per-scale-set failures, and that the configurator would stay a pure broker. Rejected because the
inputs and the credentials are on the configurator, the concrete lifecycle gap (orphaned groups)
is closed by explicit deletion, and the `garm` charm would gain an OpenStack client it otherwise
does not need. Worth revisiting if the group ever becomes provider-scoped rather than
scale-set-scoped, or if GARM-only data has to drive the rules.

**Let the operator own the group and pass it by reference.** A configuration option naming a
group, forwarded to the provider, with no cloud writes from the charm. Rejected because it does
not deliver the aim: the charm could not keep the rules right, and every scale set would need its
group created before it works. The rules are the security control, not a reference to one.

**Use the provider's `default_security_groups` configuration.** The provider applies a list to
every instance it creates. Rejected because it applies per provider rather than per scale set,
and the group still has to be created and kept right — the same work, in the same place, with
less precision.

**Enforce egress inside the runner instead of in OpenStack.** A rendered nftables ruleset in the
runner template needs no cloud permissions. Rejected as isolation: a runner runs untrusted job
code as root and can flush its own firewall, so it is defence in depth at best.

```{seealso}
{ref}`Charm reference <reference_charm_reference>` for the option, its default and the group's
lifecycle, and the Juju charm reference for the
[configurator](https://canonical.com/juju/docs/juju-cli/3.6/reference/charm/#configurator-charm)
and
[integrator](https://canonical.com/juju/docs/juju-cli/3.6/reference/charm/#integrator-charm)
definitions.
```
