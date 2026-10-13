---
myst:
  html_meta:
    "description lang=en": "Reference for the GARM charm's OWASP security event feed, its log selector, the read-only access role, and the forwarding paths."
---

(reference_security_logs)=

# Security event logging

This page describes the OWASP-structured security event feed emitted by the
`garm` charm: the shape of each event, the selector that isolates the feed, the
read-only access role that consumes it, and the paths by which events reach the
observability backend. For the overall security posture, see the
{ref}`security reference <reference_security>`.

## Event envelope

The `garm` charm emits OWASP-structured security events and forwards them to Loki
over the `logging` (`loki_push_api`) relation provided by the `go-framework`
Charmcraft extension. Each event is a JSON object nested under an `owasp_event`
key, carrying `type: "security"` and `appid: "canonical.garm"`. Read access to
these events is decoupled from Juju operational rights to satisfy least
privilege.

## Log selector

Because `appid` and `type` are nested JSON fields rather than Loki stream labels,
the feed is isolated with a LogQL query that parses the JSON:

```
{juju_application="garm"} | json | owasp_event_appid="canonical.garm" | owasp_event_type="security"
```

## Read-only access role

Security personnel, auditors, and monitoring tools consume the feed through a
**read-only** role in the observability backend (Grafana/Loki, or the customer
SIEM) scoped to the security feed. This role grants no Juju model access and no
ability to modify the deployment:

- Grafana: a Viewer-role user on the Loki datasource, restricted to the security
  dashboard/folder.
- Direct Loki: a read-only tenant/API token scoped to the garm application
  stream, with the `| json` filter above applied to the security feed.

## Juju RBAC boundary

The privileged operational surfaces remain governed by Juju RBAC and are not
exposed to the read-only access role:

- the `get-credentials` Juju action (discloses admin credentials), and
- the admin-credentials Juju secret.

Observing that an `authz_admin:...,get_credentials` event *occurred* is a
read-only audit capability; performing the action itself requires Juju
privileges.

## Forwarding paths

Two log origins reach Loki by different paths:

- **Workload logs** (the GARM Go application) are written to the workload's
  standard output and collected by the `go-framework` `LogForwarder` over the
  `logging` relation. This path is active once the charm is integrated with
  Loki:

  ```
  juju deploy loki-k8s --channel=1/stable loki
  juju integrate garm:logging loki:logging
  ```

  The feed is then queried on Loki with the log selector shown above.

- **Charm-hook logs** (`sys_startup`, `sys_shutdown`, and the `get-credentials`
  action, all emitted from the charm's Python hook process) are written to
  `juju-log`, which Juju forwards to the Juju controller. Their onward handling,
  retention, and forwarding is therefore the responsibility of the Juju
  controller operator rather than this charm. On the controller, these events
  are visible with `juju debug-log`:

  ```
  juju debug-log --include unit-garm-0 | grep owasp_event
  ```

## Related information

- {ref}`Security reference <reference_security>`
- {ref}`Security overview <explanation_security>`
- {ref}`How to secure GARM <how_to_secure_garm>`
