---
myst:
  html_meta:
    "description lang=en": "Security posture and responsibilities for the GARM and GARM configurator charms."
---

(explanation_security)=

# Security in the GARM charms

This page describes the security posture of the ``garm`` and
``garm-configurator`` charms. It focuses on controls implemented by the charms,
their trust boundaries, and the actions expected from an operator.

It does not replace the security documentation for Juju, Kubernetes,
PostgreSQL, OpenStack, GitHub, or the GARM application. Those systems own the
security controls that they provide. The statements here describe charm behavior
that is evidenced in this repository; they do not make claims about the security
implementation of external services.

## Security boundaries

In this documentation, "deployment" means the arrangement described in the
{ref}`architecture overview <reference_charm_architecture_deployment>`: the
GARM and GARM configurator charms, PostgreSQL, the deployment network, and the
external GitHub and OpenStack services they use.

The deployment has these main boundaries:

- Juju stores charm configuration and secrets.
- The ``garm`` charm runs GARM and connects it to PostgreSQL.
- The ``garm-configurator`` charm publishes one scale-set configuration to GARM.
- GARM communicates with GitHub and OpenStack and manages runner VMs.
- The GARM API and metrics endpoint are exposed through the deployment network.

See the {ref}`architecture overview <reference_charm_architecture_deployment>`
for the component relationships and the {ref}`security reference <reference_security>`
for interfaces and security-sensitive options.

## Controls provided by the charms

The charms provide these controls:

- Credentials are stored in Juju secrets rather than ordinary charm
  configuration where the charm supports secret configuration.
- The configurator sends secret references over the GARM relation for the
  GitHub App private key and OpenStack password.
- The GARM charm creates its application-owned secrets on the leader and uses
  authenticated requests for GARM reconciliation.
- The GARM entrypoint writes sensitive configuration files with restricted
  permissions and removes selected sensitive environment variables before
  starting GARM.
- Security-sensitive charm configuration and relation values are checked for
  required fields, supported values, ranges, paths, and unsafe newlines where
  the charm implements those checks.
- GARM reconciles desired state and drains scalesets during charm removal.

These controls reduce exposure and configuration errors. They do not replace
access control or transport security provided by the deployment environment or
by GARM itself.

## Authentication and secrets

GARM creates an administrator account during first-run setup. The credentials
are stored in the ``garm-admin-credentials`` Juju secret. The
``get-credentials`` action returns those credentials to an authorized Juju
operator, so its output must be handled as secret material.

The configurator consumes the operator-provided OpenStack password and GitHub
App private key from Juju secrets. It refreshes those secret revisions when a
secret changes and publishes secret references to GARM. The GARM charm also
receives PostgreSQL connection credentials through the PostgreSQL relation and
includes them in the workload configuration.

## Risks and operator responsibilities

- GARM's workload API and metrics share port 8080. The workload does not
  terminate TLS, so externally reachable traffic needs a TLS-terminating
  ingress and a restricted network path.
- The charm derives metadata, callback, webhook, and agent URLs from its
  application base URL. A non-HTTPS base URL permits an insecure agent URL;
  remote-shell safety therefore depends on using an HTTPS agent path.
- Metrics are not authenticated by GARM. Restrict the metrics path to the
  monitoring system.
- The ``enable-shell`` option is enabled by default in the configurator
  metadata. Disable it unless an interactive runner session is required.
  Enable it only when the GARM agent path is protected by TLS and administrator
  access is restricted.
- ``pre-install-scripts`` and ``pre-job-script`` are trusted operator-supplied
  shell code. Review them before applying the configuration.
- Optional integrations are trust boundaries. Document the participating
  application and exchanged capability without assuming that the integration
  provides security controls automatically.

Use the {ref}`secure-operation how-to <how_to_secure_garm>` to apply the
operator-facing recommendations.

## Data and observability

GARM stores its operational state in PostgreSQL. Charm configuration and relation
data include scale-set settings, repository or organization targets, provider
settings, and references to secrets.

The GARM workload provides logs and metrics for configured observability
relations. The repository does not establish that an external observability
service provides retention, redaction, or alerting. Apply the observability
controls required by the deployment and do not treat the metrics endpoint as
an administrative API.

## Lifecycle and vulnerability reporting

The GARM charm attempts to disable, drain, and remove managed scalesets
during application removal when the required API and credentials are
available. If cleanup cannot complete, removal is blocked or fails and must be
retried after the reported problem is resolved. Verify resource cleanup and
credential revocation as part of the deployment's removal process.

Releases move through Charmhub risk levels with automated testing and human
promotion gates. See the {ref}`release and promotion process <release_process>`.

Report security issues through the repository's
[security policy](https://github.com/canonical/github-runner-operators/blob/main/SECURITY.md).

## Related information

- {ref}`Security reference <reference_security>`
- {ref}`How to secure GARM <how_to_secure_garm>`
- {ref}`Architecture overview <reference_charm_architecture_deployment>`
- {ref}`Charm reference <reference_charm_reference>`
