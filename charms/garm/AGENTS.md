# AGENTS.md — garm charm

GARM (GitHub Actions Runner Manager) charm. Read the root `AGENTS.md` first for the shared
charm conventions; this file lists only what's specific to `garm`.

- **Base: `paas_charm.go.Charm`.** Do **not** add a `_reconcile` method — the base class
  reconciles. Inject behaviour by overriding `restart()`, which writes the GARM TOML config,
  sets the Pebble command, and triggers admin first-run (`_maybe_first_run`).
- **Readiness gate**, don't defer: `restart()` returns early when `not self.is_ready()` and
  sets a `BlockedStatus` when PostgreSQL relation data is missing (`_get_postgresql_config`
  returns `None`).
- **Owner of two labelled juju secrets** — `GARM_SECRETS_LABEL` and
  `GARM_ADMIN_CREDENTIALS_LABEL` — created leader-only in `_ensure_secrets`. As the **owner**,
  read them with plain `get_content()` (`_get_secrets`, `_get_admin_credentials`); `refresh=True`
  is an observer concept and is not needed here (see root `AGENTS.md`).
- **Domain logic is factored out of `charm.py`**: `src/garm_api.py` and `src/garm_client/`
  (the GARM HTTP client). Extend these rather than growing the charm class. TOML rendering:
  `render_garm_toml()` in `src/charm.py`.
- GARM serves its API and `/metrics` on one fixed port (`GARM_PORT`); the `app-port` /
  `metrics-port` / `metrics-path` config options have no effect (the charm logs a warning
  rather than blocking). The port is pinned in the `_workload_config` property.
- Tests: unit in `tests/unit/`; integration via `tox -e garm-integration`
  (`charms/tests/integration/test_garm.py`).
