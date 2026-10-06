# Security Logs Viewer — read-only access to garm security events

The `garm` charm emits OWASP-structured security events and forwards them to Loki
over the `logging` (`loki_push_api`) relation that the `go-framework` charmcraft
extension provides. Each event is a JSON object nested under an `owasp_event` key,
carrying `type: "security"` and `appid: "canonical.garm"`. To satisfy
least-privilege (SSDLC §1.2), read access to these events is decoupled from Juju
operational rights.

## Decoupled read-only role

Grant security personnel, auditors, and monitoring tools a **read-only** role in
the observability backend (Grafana/Loki, or the customer SIEM) scoped to the
security feed — filter on `owasp_event.appid="canonical.garm"` and
`owasp_event.type="security"`. This role grants no Juju model access and no ability
to modify the deployment.

- Grafana: a Viewer-role user on the Loki datasource, restricted to the security
  dashboard/folder.
- Direct Loki: a read-only tenant/API token scoped to the
  `{appid="canonical.garm"}` stream.

## What stays governed by Juju RBAC (not log access)

The privileged operational surfaces remain controlled by Juju RBAC and must NOT be
exposed to the log-viewer role:

- the `get-credentials` Juju action (discloses admin credentials), and
- the admin-credentials Juju secret.

Viewing that an `authz_admin:...,get_credentials` event *occurred* is a read-only
audit capability; performing the action requires Juju privileges.

## Forwarding path and verification

The `go-framework` extension already instantiates a `loki_push_api` `LogForwarder`
on the `logging` relation, so no charm-specific forwarder is declared. Relate the
charm to Loki to activate forwarding:

```
juju deploy loki-k8s --channel=1/stable loki
juju integrate garm:logging loki:logging
```

Then generate a security event (for example, run the `get-credentials` action) and
confirm the `owasp_event.type="security"` / `owasp_event.appid="canonical.garm"`
line reaches Loki (query in Grafana/Loki). Security events emitted from the charm
hook process are delivered to `juju-log`; confirm on your deployment topology that
they are forwarded, and if charm-process lines are not captured by the workload log
forwarder, route the events to a workload-container file sink and add an
OpenTelemetry Collector `filelog` receiver per the `owasp-logger` documentation.
