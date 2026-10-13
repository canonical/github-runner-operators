---
myst:
  html_meta:
    "description lang=en": "Security-sensitive behavior and defaults for the GARM and GARM configurator charms."
---

(reference_security)=

# Security reference

This page describes security-sensitive behavior and defaults implemented by the
``garm`` and ``garm-configurator`` charms. For the overall security posture and
operator responsibilities, see the {ref}`security overview <explanation_security>`.

## Charm controls

- GARM creates application-owned Juju secrets for its JWT, database passphrase,
  and administrator credentials.
- The configurator reads the OpenStack password and GitHub App private key from
  Juju secret configuration and publishes secret references to GARM.
- The ``get-credentials`` action returns GARM administrator credentials and
  should be treated as a sensitive operation.
- GARM validates selected required fields and runner options. The charms do not
  apply a general validation pass to every relation value before reconciliation;
  review values such as scale-set names, flavors, OS architecture, and scripts
  as trusted inputs.

## Security-sensitive defaults and boundaries

- GARM serves its API and metrics on port 8080. The workload does not terminate
  TLS; use a TLS-terminating ingress for external access.
- The charm derives metadata, callback, webhook, and agent URLs from its
  application base URL. A non-HTTPS base URL permits an insecure agent URL.
- Metrics authentication is disabled by GARM. Restrict the metrics path to the
  monitoring system.
- ``enable-shell`` is enabled by default in the configurator metadata. Disable
  it unless an interactive runner session is required.
- The configurator accepts HTTP and HTTPS URL syntax for supported URL options.
  URL syntax validation does not guarantee encrypted transport.
- ``pre-install-scripts`` and ``pre-job-script`` are trusted operator-supplied
  shell code.

## Removal and vulnerability reporting

GARM removal attempts scaleset and runner cleanup when its API and credentials
are available. If cleanup cannot complete, removal is blocked or fails and must
be retried after the reported problem is resolved. The charms do not document
complete credential revocation or secure erasure.

Report security issues through the repository's
[security policy](https://github.com/canonical/github-runner-operators/blob/main/SECURITY.md).

## Related information

- {ref}`Security overview <explanation_security>`
- {ref}`How to secure GARM <how_to_secure_garm>`
- {ref}`Architecture overview <reference_charm_architecture_deployment>`
- {ref}`Charm reference <reference_charm_reference>`
