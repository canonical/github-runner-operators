# GARM Sigma detection rules

Vendor-neutral [Sigma](https://sigmahq.io) rules for the security events emitted by
the `garm` charm (`appid: canonical.garm`, `type: security`). Author once here;
convert to your SIEM's query language with `sigma-cli` / pySigma.

## Field mapping (OWASP → Sigma selectors)

The `owasp-logger` library emits each event as a JSON object **nested under an
`owasp_event` key**, so rules select on dotted `owasp_event.*` field names.

| OWASP field | Sigma selector key | Example |
| --- | --- | --- |
| `event` | `owasp_event.event` | `owasp_event.event\|startswith: 'authz_fail'` |
| `level` | `owasp_event.level` | `owasp_event.level: 'CRITICAL'` |
| `appid` | `owasp_event.appid` / `logsource.product` | `canonical.garm` |

The `event` value is a flat token of the form `<event_name>:<comma-separated-args>`
(for example `authz_fail:garm-admin,<resource>` or
`authz_admin:garm/0,get_credentials`), so rules match it with `startswith` /
`contains`.

## Validate & apply

```bash
pip install sigma-cli
sigma check docs/security/sigma/garm/
# Convert to Loki (LogQL), for example:
sigma convert -t loki docs/security/sigma/garm/authz_fail_unauthorized.yml
```

Correlation rules (`authn_login_fail_bruteforce.yml`) require pySigma ≥ 0.11 and a
backend that supports correlation (Loki/LogQL, Elasticsearch). Check your converter.

## Rules

| File | Event | Detects |
| --- | --- | --- |
| `authz_fail_unauthorized.yml` | `authz_fail` | 401 authorization rejection from the GARM admin API |
| `authn_login_fail_bruteforce.yml` | `authn_login_fail` | Burst of failed admin logins (brute force) |
| `credential_removed.yml` | `authn_token_delete` | Deletion of a stored forge credential |
| `admin_credentials_disclosed.yml` | `authz_admin` | `get-credentials` action disclosing admin credentials |
| `unexpected_shutdown.yml` | `sys_shutdown` | Application teardown / resource drain before removal |

## Lifecycle

Rules are version-controlled and updated/validated/merged with the product release
cycle. SecOps pulls validated rules directly from this directory.
