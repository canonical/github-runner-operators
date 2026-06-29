# AGENTS.md — planner-operator charm

GitHub runner planner API charm. Read the root `AGENTS.md` first; this file lists only what's
specific to `planner-operator`.

- **Base: `paas_charm.go.Charm`** — `restart()` is the reconcile. Don't implement a separate reconcile; rely on `restart()`.
  - **DON'T** write a `_reconcile` method that implements its own reconcile logic — `restart()` already is the reconcile. A thin dispatcher that just calls `self.restart()` is fine.
  - **DO** override framework hooks (always wrapping `super()`): `_create_app()` injects OpenTelemetry environment variables, and `restart()` holistically syncs the planner relation endpoints on every restart.
- **Sharing credentials over a relation** (see `_create_relation_credentials`):
  - **DO** put the secret **id** in the databag, not the token — `add_secret({"token": …}, label=…)` → `secret.grant(relation)` → `relation.data[self.app]["token"] = str(secret.id)`.
  - **DO** clean up orphaned tokens with `remove_all_revisions()` (`_delete_orphaned_credentials`).
- The Go workload lives in `cmd/planner/` + `internal/`; charm changes that affect the API
  often pair with changes there.
- Tests: unit in `tests/unit/`; integration via `tox -e planner-integration`.
