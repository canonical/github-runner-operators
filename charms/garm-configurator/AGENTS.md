# AGENTS.md — garm-configurator charm

Configuration broker for GARM scalesets. Read the root `AGENTS.md` first; this file lists only
what's specific to `garm-configurator`.

- **Base: plain `ops.CharmBase`** — the only direct-`ops` charm in the repo (no `go-framework`
  extension, no `paas_charm`). The canonical charm-engineer patterns apply here directly.
- **Holistic single `_reconcile` is correct here.** Every observed event funnels into
  `_reconcile` (`GarmConfiguratorCharm.__init__`); it builds full state via
  `CharmState.from_charm(self)`, forwards OpenStack credentials and scaleset config to the
  relations, and sets unit status **once at the end**.
  - **DON'T** add per-event delta handlers.
- **State + secret resolution live in `src/charm_state.py`** (`CharmState`,
  `CharmConfigInvalidError`). This is also the repo's reference for the **observer** secret
  pattern: the `*.from_charm` resolvers read operator-supplied secret config (OpenStack
  password, GitHub App private key) with `get_content(refresh=True)` because the *operator*
  owns those secrets — `refresh=True` picks up the new revision on `secret-changed`. Validate
  there and raise `CharmConfigInvalidError`; `_reconcile` turns it into a `BlockedStatus`.
- Relation databags are string-only: serialise structured values (e.g. `pre_install_scripts`
  via `json.dumps`).
- Tests: Scenario-based unit tests in `tests/unit/test_charm.py`; integration via
  `tox -e garm-configurator-integration`.
