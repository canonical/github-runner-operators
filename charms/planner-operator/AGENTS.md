# AGENTS.md — planner-operator charm

GitHub runner planner API charm. Read the root `AGENTS.md` first; this file lists only what's
specific to `planner-operator`.

- **Base: `paas_charm.go.Charm`.** Do **not** add a `_reconcile` method — the base class
  reconciles. This charm overrides two framework hooks (always wrapping `super()`):
  `_create_app()` injects OpenTelemetry environment variables, and `restart()` holistically
  syncs the planner relation endpoints on every restart.
- **Sharing credentials over a relation**: create a labelled secret, grant it to the relation,
  and put the secret **id** (not the token) in the databag —
  `add_secret({"token": …}, label=…)` → `secret.grant(relation)` →
  `relation.data[self.app]["token"] = str(secret.id)` (see `_create_relation_credentials`).
  Clean up orphaned tokens with `remove_all_revisions()` (`_delete_orphaned_credentials`).
- The Go workload lives in `cmd/planner/` + `internal/`; charm changes that affect the API
  often pair with changes there.
- Tests: unit in `tests/unit/`; integration via `tox -e planner-integration`.
