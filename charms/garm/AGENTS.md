# AGENTS.md — garm charm

GARM (GitHub Actions Runner Manager) charm. Read the root `AGENTS.md` first for the shared
charm conventions; this file lists only what's specific to `garm`.

- **Base: `paas_charm.go.Charm`** — `restart()` is the reconcile. Don't implement a separate reconcile; rely on `restart()`.
  - **DON'T** write a `_reconcile` method that implements its own reconcile logic — `restart()` already is the reconcile.
  - **DO** register a thin `_reconcile` dispatcher (just calls `self.restart()`) and point all garm-specific hook observers at it, so every hook flows through one entry point.
  - **DO** override `restart()` to inject behaviour: it writes the GARM TOML config, sets the Pebble command, and triggers admin first-run (`_maybe_first_run`).
  - **DO** call `_ensure_secrets()` before the `is_ready()` gate inside `restart()`, so secrets are created on `install`/`leader_elected` before pebble is ready.
- **DO** gate on readiness; **DON'T** defer: `restart()` returns early when `not self.is_ready()`, and short-circuits by reporting a status when PostgreSQL relation data is missing (`_get_postgresql_config` returns `None`).
- **Secrets (owner).** `garm` owns two labelled juju secrets — `GARM_SECRETS_LABEL` and `GARM_ADMIN_CREDENTIALS_LABEL` — created leader-only in `_ensure_secrets`.
  - **DO** read them with plain `get_content()` (`_get_secrets`, `_get_admin_credentials`).
  - **DON'T** pass `refresh=True` — that's an observer concept (see root `AGENTS.md`).
- **Domain logic is factored out of `charm.py`**: `src/garm_api.py` and `src/garm_client/`
  (the GARM HTTP client). Extend these rather than growing the charm class. TOML rendering:
  `render_garm_toml()` in `src/charm.py`.
- GARM serves its API and `/metrics` on one fixed port (`GARM_PORT`); the `app-port` /
  `metrics-port` / `metrics-path` config options have no effect (the charm logs a warning
  rather than blocking). The port is pinned in the `_workload_config` property.
- Tests: unit in `tests/unit/`; integration via `tox -e garm-integration`
  (`charms/tests/integration/test_garm.py`).
