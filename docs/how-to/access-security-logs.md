---
myst:
  html_meta:
    "description lang=en": "Learn how to grant and use read-only access to the GARM charm's OWASP security event feed."
---

(how_to_access_security_logs)=

# How to access GARM security logs

The `garm` charm emits OWASP-structured security events and forwards them to Loki
over the `logging` (`loki_push_api`) relation that the `go-framework` charmcraft
extension provides. Each event is a JSON object nested under an `owasp_event` key,
carrying `type: "security"` and `appid: "canonical.garm"`. To satisfy
least-privilege, read access to these events is decoupled from Juju
operational rights.

## Decoupled read-only role

Grant security personnel, auditors, and monitoring tools a **read-only** role in
the observability backend (Grafana/Loki, or the customer SIEM) scoped to the
security feed. Because `appid` and `type` are nested JSON fields (not Loki stream
labels), select the feed with a LogQL query that parses the JSON:

```
{juju_application="garm"} | json | owasp_event_appid="canonical.garm" | owasp_event_type="security"
```

This role grants no Juju model access and no ability to modify the deployment.

- Grafana: a Viewer-role user on the Loki datasource, restricted to the security
  dashboard/folder.
- Direct Loki: a read-only tenant/API token scoped to the garm application stream,
  with the `| json` filter above applied to the security feed.

## What stays governed by Juju RBAC (not log access)

The privileged operational surfaces remain controlled by Juju RBAC and must NOT be
exposed to the log-viewer role:

- the `get-credentials` Juju action (discloses admin credentials), and
- the admin-credentials Juju secret.

Viewing that an `authz_admin:...,get_credentials` event *occurred* is a read-only
audit capability; performing the action requires Juju privileges.

## Forwarding path and verification

Two log origins reach Loki by different paths:

- **Workload logs** (the GARM Go application) are written to the workload's standard
  output and collected by the `go-framework` `LogForwarder` over the `logging`
  relation. Relate the charm to Loki to activate this path:

  ```
  juju deploy loki-k8s --channel=1/stable loki
  juju integrate garm:logging loki:logging
  ```

- **Charm-hook logs** (`sys_startup`, `sys_shutdown`, and the `get-credentials`
  action, all emitted from the charm's Python hook process) are written to
  `juju-log`, which Juju forwards to the Juju controller. Their onward handling,
  retention, and forwarding is therefore the responsibility of the Juju controller
  operator rather than this charm.

To verify the workload path, generate a workload-origin security event and confirm
the record reaches Loki:

```
{juju_application="garm"} | json | owasp_event_appid="canonical.garm" | owasp_event_type="security"
```

Charm-hook security events (for example, from running the `get-credentials` action)
are visible on the controller with `juju debug-log`:

```
juju debug-log --include unit-garm-0 | grep owasp_event
```
