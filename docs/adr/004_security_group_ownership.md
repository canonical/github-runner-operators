---
title: ADR-004 - policy in the configurator, security group lifecycle in the GARM charm
author: Yangsoo Yoon (yangsoo.yoon@canonical.com)
date: 2026/10/20
domain: architecture
replaced-by:
---

# Policy in the configurator, security group lifecycle in the GARM charm

A `garm-configurator` charm describes one scale set and publishes that description over a
relation; the `garm` charm acts on it. The security group that isolates a scale set's runners
splits along that line: the configurator owns the rules as configuration, and the GARM charm
creates, maintains, and deletes the group. This ADR records why, because creating a resource in
a cloud is what Juju calls an
[integrator charm](https://canonical.com/juju/docs/juju-cli/3.6/reference/charm/#integrator-charm),
while the charm doing it here is the one Juju calls a
[configurator charm](https://canonical.com/juju/docs/juju-cli/3.6/reference/charm/#configurator-charm).

## Context

Juju defines a configurator charm as a workloadless charm that configures another charm once
they are integrated, and an integrator charm as a proxy charm whose non-charmed workload is
cloud functionality. The categories nest — an integrator is a kind of proxy charm, which is a
kind of configurator — and what separates them in practice is where the effect lands.

A scale set's security group outlives the runners it was created for: OpenStack attaches a group
to a port for the life of the virtual machine. Whoever manages the group therefore has to answer
two questions that only the scale set's own lifecycle can answer: when is the group safe to
delete, and what happens when the scale set is renamed or removed.

The configurator cannot answer either. It knows the definition, not the runners. It can delete on
opt-out and on its own removal, and it must tolerate "still in use" indefinitely; a rename leaves
the group behind, because the charm keeps no record of the previous name. The GARM charm does
know: it retires a generation, drains it, removes its runners, and deletes the scale set only
after GARM reports none left — the exact moment the group becomes safe to delete.

Earlier in this work the opposite split was implemented: the configurator created and converged
the group and published its id. It worked, but it accumulated the lifecycle problem described
above, and it gave the configurator an OpenStack client, permissions, and a network path it
otherwise never needed.

## Decision

The configurator owns the policy. It validates `security-group-rules` and publishes them on the
relation, so the rules are modelled in Juju — typed, validated, visible in `juju config` and the
Terraform module — and an invalid combination is rejected before anything reaches the cloud.

The GARM charm owns the lifecycle. It creates `garm-<scale set name>`, keeps its rules equal to
the published list, passes the id to the provider as the scale set's `security_groups` extra
spec, and deletes the group once no scale set claims it: after a rename or a removal, and after
the drained scale set is gone.

Each side keeps what it needs to do its part:

* The configurator needs no cloud credentials, no permissions, and no network path to OpenStack,
  and stays a configurator.
* The GARM charm already receives the tenant credentials to render the provider's configuration,
  already reaches OpenStack through the provider it runs, and already owns the scale set's
  create, drain, and delete path.

The group's name is derived from the scale set name on both sides, so moving the management kept
the resource identical: an upgrade reuses the group the configurator created rather than
replacing it.

## Consequences

* A failed OpenStack reconcile fails closed. The scale sets of that tenant are claimed but left
  alone for the pass, so they are neither created without their group nor mistaken for orphans,
  and the unit reports it in its status.
* The GARM charm gains an OpenStack client and the permissions to create and delete groups and
  their rules. A role without delete permission still works: groups it cannot remove are logged
  and left.
* A group a port still attaches cannot be deleted. That is expected for some time after a scale
  set is removed, because OpenStack removes the port asynchronously, so it is logged at info and
  retried on a later reconcile.
* Runners that already exist keep the group they were launched with. A changed group reaches new
  runners only; existing ones pick it up as they are replaced.
* Removing only the configurator takes its credentials away before the GARM charm can delete the
  remaining groups. Remove the GARM application too, or delete the groups by hand. The removal
  path retries a group whose port is still being removed, because nothing runs after it.
* The GARM charm must be upgraded before the configurator that publishes rules: a GARM charm
  given a configurator that predates this split sees no rules, and treats the scale set as one it
  must not touch rather than sweeping a group it does not know about.
* Scale set names must be unique within a project: the group is named after the scale set, and
  two deployments using one name would share a group and keep removing each other's rules.

## Alternatives considered

**The configurator manages the group**, as this branch first implemented. It keeps every input
and the credentials in one place, and the relation remains a pure id hand-over. Rejected on
lifecycle: the configurator cannot see runner ports, so it cannot know when a group is safe to
delete, and a rename or its own removal leaves the group behind against the project's quota.

**The operator creates the group and passes it by reference.** A configuration option naming a
group, forwarded to the provider, with no cloud writes from either charm. Rejected because it
does not deliver the aim: neither charm could keep the rules right, and every scale set would
need its group created before it works. The rules are the security control, not a reference to
one.

**The provider's `default_security_groups` configuration.** The provider applies a list to every
instance it creates. Rejected because it applies per provider rather than per scale set, and the
group still has to be created and kept right — the same work, in the same place, with less
precision.

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
