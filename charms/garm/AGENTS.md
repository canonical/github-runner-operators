# AGENTS.md — garm charm

GARM (GitHub Actions Runner Manager) charm. Read the root `AGENTS.md` first for the shared
charm conventions; this file lists only what's specific to `garm`.

- **Base: `paas_charm.go.Charm`** — `restart()` is the reconcile. Don't implement a separate reconcile; rely on `restart()`. A thin `_reconcile` wrapper that just calls `self.restart()` is fine.
  - **DO** override `restart()` to inject behaviour: it writes the GARM TOML config, sets the Pebble command, and triggers admin first-run (`_maybe_first_run`).
- **DO** gate on readiness; **DON'T** defer: `restart()` returns early when `not self.is_ready()`, and short-circuits by reporting a status when PostgreSQL relation data is missing (`_get_postgresql_config` returns `None`).
- **Secrets (owner).** `garm` owns two labelled juju secrets — `GARM_SECRETS_LABEL` and `GARM_ADMIN_CREDENTIALS_LABEL` — created leader-only in `_ensure_secrets`.
  - **DO** read them with plain `get_content()` (`_get_secrets`, `_get_admin_credentials`).
  - **DON'T** pass `refresh=True` — that's an observer concept (see root `AGENTS.md`).
- **Domain logic is factored out of `charm.py`**: `src/garm_api.py` and `src/garm_client/`
  (the GARM HTTP client), the per-resource reconcilers (`src/github_reconciler.py`,
  `src/entity_reconciler.py`, `src/scaleset_reconciler.py`), and relation-derived desired state
  (`src/charm_state.py` — `CharmState.from_charm`). Extend these rather than growing the charm
  class. TOML rendering: `render_garm_toml()` in `src/charm.py`.
  - **Relation-/config-derived value objects belong in `src/charm_state.py`** (per
    [ISD014](https://discourse.charmhub.io/t/specification-isd014-managing-charm-complexity/11619)):
    keep desired-state types parsed from relation or config data (`CharmState`, `SSHDebugInfo`,
    `RunnerConfig`) there. **DON'T** define them in rendering/helper modules — e.g.
    `runner_template.py` only *renders* a `RunnerConfig`, it doesn't own it. Rendering and
    reconciler modules import these types; **DO** keep `charm_state.py` free of
    rendering/reconciler imports so it can't form an import cycle.
- **`src/garm_client/` is generated** by `scripts/generate_client.sh` (openapi-generator) —
  **DON'T** hand-edit it. The pin (`GARM_COMMIT`) is at a GARM revision that includes upstream's
  `swagger:strfmt byte` fix (GARM PR #802), so Go `[]byte` fields — the template `data` body and
  `GithubApp.private_key_bytes` — are declared `type: string, format: byte` in the spec and
  generate as base64 strings directly; no local swagger patch is needed. These base64 strings
  are produced at the API boundary: `garm_api.py` base64-encodes `data` on create/update, and
  `github_reconciler.py` base64-encodes the raw PEM private key (held as `CredentialSpec.private_key`)
  when building the `GithubApp` model. To fix a generated-type issue, bump `GARM_COMMIT` and
  re-run the script, never hand-edit the output.
- GARM serves its API and `/metrics` on one fixed port (`GARM_PORT`); the `app-port` /
  `metrics-port` / `metrics-path` config options have no effect (the charm logs a warning
  rather than blocking). The port is pinned in the `_workload_config` property.
- Tests: unit in `tests/unit/`; integration via `tox -e garm-integration`
  (`charms/tests/integration/test_garm.py`).
