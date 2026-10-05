---
myst:
  html_meta:
    "description lang=en": "How to apply the security settings and operating practices for the GARM charms."
---

(how_to_secure_garm)=

# How to secure GARM and the GARM configurator

Use this guide to apply the charm-level security recommendations before using
GARM for production workloads.

## What you'll need

- A deployed ``garm`` application and at least one ``garm-configurator``
  application.
- Permission to change Juju application configuration.
- A deployment ingress that can provide HTTPS for externally reachable GARM
  traffic.
- Juju secret values for the GitHub App and OpenStack credentials.

This guide covers charm settings and assumptions. Follow the platform's
canonical documentation for ingress, Juju access control, PostgreSQL, and
OpenStack hardening.

## Protect the GARM endpoint

GARM listens on port 8080 for its API and metrics. The workload does not
terminate TLS. Expose it through a TLS-terminating ingress and restrict the
backend and metrics paths to their intended clients.

Do not treat the unauthenticated metrics endpoint as an administrative API.
Restrict it to the monitoring system.

## Disable the remote shell unless required

The configurator declares ``enable-shell`` enabled by default. Disable it when
interactive runner sessions are not required:

```bash
juju config garm-configurator enable-shell=false
```

Verify the applied value:

```bash
juju config garm-configurator enable-shell
```

The command should report ``false``. If the remote shell is required, use a
TLS-protected GARM agent path and restrict GARM administrator access.

## Protect credentials

Use Juju secrets for the GitHub App private key and OpenStack password.

The ``get-credentials`` action returns the GARM administrator password. Run it
only when needed and treat its output as secret material:

```bash
juju run garm/0 get-credentials
```

For the complete first-deployment secret flow, see the
[deployment tutorial](../tutorial/garm.md).

## Review trusted script settings

Treat these options as trusted shell-code inputs:

- ``pre-install-scripts``;
- ``pre-job-script``.

Review every change before applying it. Clear an option when it is no longer
needed:

```bash
juju config garm-configurator pre-install-scripts="" pre-job-script=""
```

## Verify the charm state

Check that the charms have the expected status after changing security
settings:

```bash
juju status
```

A failed or blocked status requires resolving the reported configuration or
relation problem before relying on the deployment.

## Related information

- [Security in the GARM charms](../explanation/security.md)
- [Charm reference](../reference/charms.md)
- [How to retrieve GARM admin credentials](retrieve-garm-credentials.md)
- [Release and promotion process](../explanation/charm-release-and-promotion.md)
