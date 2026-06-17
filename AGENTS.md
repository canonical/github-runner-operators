# AGENTS.md

Guidance for AI agents working in this monorepo. Keep changes surgical and idiomatic to
the surrounding code. This file complements — and does not restate — the Copilot-specific
guidance in `.github/instructions/` and the human-facing `CONTRIBUTING.md`.

## Repository map

| Path | Contents |
| --- | --- |
| `charms/` | Four Juju charms (see below) plus shared integration tests in `charms/tests/integration/`. |
| `cmd/` | Go application entry points: `planner`, `webhook-gateway`. |
| `internal/` | Shared Go packages (`database`, `github`, `planner`, `queue`, `server`, `telemetry`, `webhook`, …) — the application logic the paas charms package and deploy. |
| `bundles`, `images` | Juju bundles and rock/image definitions. |
| `docs/` | Diátaxis-structured docs (Read the Docs). ADRs in `docs/adr/`. |
| `actions/`, `runner_grafana_dashboards/` | A GitHub Action and runner-host dashboards. |
| `parts`, `prime`, `stage`, `**/lib/charms/**` | **Generated or vendored — do not edit.** `lib/charms/**` is auto-updated; see `.github/instructions/charms-lib-updates.instructions.md`. |

The Go layout follows the [community Go project layout](https://github.com/golang-standards/project-layout).
`README.md` has the canonical layout (note: it predates the `garm` and `garm-configurator`
charms — there are four charms, not two).

### Charms

| Charm | Base | Role |
| --- | --- | --- |
| `garm` | `paas_charm.go.Charm` | GARM (GitHub Actions Runner Manager) — 12-factor, PostgreSQL, OpenStack provider. |
| `planner-operator` | `paas_charm.go.Charm` | Runner planner API — 12-factor Go app. |
| `webhook-gateway-operator` | `paas_charm.go.Charm` | GitHub webhook receiver/forwarder — 12-factor Go app. |
| `garm-configurator` | `ops.CharmBase` | Config broker for GARM scalesets. The **only** direct-`ops` charm. |

## Build & test

- **Per-charm Python checks** — from the charm directory, `tox -c tox.toml` (envs `fmt`, `lint`, `complexity`, `static`, `unit`, `coverage-report`; ruff, codespell, pyright, pytest+coverage). CI runs these per charm via `tox -c tox.toml`.
- **Integration tests** (root `tox.ini`) — `tox -e <charm>-integration` (`garm`, `webhook-gateway`, `planner`, `garm-configurator`) or `tox -e charms-integration` for all. Requires a live Juju model (jubilant + pytest-operator).
- **`actions/` Python** — `tox -e actions-lint`, `tox -e actions-static`, `tox -e actions-unit`.
- **Go** — `go test ./...`.
- `charmcraft pack` — build a charm (run from the charm dir; not wired into tox).
- Gates from `CONTRIBUTING.md`: **≥ 85% coverage** on internal packages, **cyclomatic complexity < 10** per function.

## Charm conventions

These are **K8s 12-factor charms** on the `go-framework` charmcraft extension: a thin Python
charm layer wraps a Go workload (`CONTRIBUTING.md` §"12 factor"; each `charmcraft.yaml`).
`garm-configurator` is the exception — a plain `ops` charm.

### Holistic state handling — but don't add a second reconcile

Charm logic should read full current state, act idempotently, and set unit status once.

- **`paas_charm` charms (`garm`, `planner-operator`, `webhook-gateway-operator`)**: the base
  class **already runs the holistic flow** (`PaasCharm.restart()`). Do **not** add a
  `_reconcile` method. To inject behaviour, **override a framework hook** and call
  `super()` — e.g. `restart()` (`garm`: write config + first-run; `planner-operator`: sync
  relation endpoints) or `_create_app()` (`planner-operator`/`webhook-gateway-operator`:
  inject OTel env). Gate on readiness with an early return (`if not self.is_ready(): return`),
  not `event.defer()`.
- **`garm-configurator`**: a single `_reconcile` that every event observes is the correct
  pattern here (`GarmConfiguratorCharm._reconcile`): build state via
  `CharmState.from_charm(self)`, write relation data, set status once at the end.

### Ops / Juju lifecycle idioms agents get wrong

- **Secrets — owner vs observer** (a common mistake): `refresh=True` is an *observer* concept —
  it advances the unit's *tracked* revision to the latest. Use it only when **consuming a
  secret you don't own** (an operator-supplied config secret, or one granted over a relation),
  especially in `secret-changed` handlers, so you read the new revision instead of the stale
  tracked one — e.g. the `*.from_charm` resolvers in `charms/garm-configurator/src/charm_state.py`.
  When you **own** the secret (created via `add_secret`), plain `get_content()` already returns
  the latest revision (and `set_content()` invalidates the cache), so `refresh=True` is
  unnecessary — e.g. `garm`'s `_get_secrets` / `_get_admin_credentials`. Use `peek_content()`
  to read the latest revision without changing tracking. The leader creates labelled secrets so
  other units can fetch them by `label`.
- **Relation data carries the secret id/URI, never the content**: `add_secret(..., label=...)`
  → `secret.grant(relation)` → `relation.data[self.app]["token"] = str(secret.id)`
  (`planner-operator`'s `_create_relation_credentials`).
- Prefer **readiness-gating** (`is_ready()` early-return) over `event.defer()`.
- Relation databags are **string-only** — serialise (e.g. `json.dumps`) structured values.

### Testing

- New unit tests use **Scenario** (`scenario.Context` / `State` / `Relation` / `Secret`),
  not `Harness` — see `charms/garm-configurator/tests/unit/`.
- Integration tests live in the shared `charms/tests/integration/`.

## 12-factor divergences from the canonical charm-engineer guidance

We borrow from the canonical
[`charm-engineer.agent.md`](https://github.com/canonical/copilot-collections/blob/main/groups/platform-engineering/agents/charm-engineer.agent.md),
but some of its rules assume a hand-written `ops` charm and do **not** apply to our paas charms:

- **No second `_reconcile`** — the `paas_charm` base class reconciles (see above).
- **No hand-authored `workload.py` / Pebble layer** — the `go-framework` extension owns the
  workload; touch Pebble only inside a `restart()` override when strictly necessary.
- **`state.py` Pydantic abstraction is optional** — only `garm-configurator` has a real
  `CharmState`; don't force it onto paas charms.

Still applicable: holistic state handling, idempotent `install`, explicit port handling, small
`try/except` blocks scoped to custom exceptions, no Canonical-internal references in charm
code, and **avoid `level=alive` health checks** in `rockcraft.yaml`.

## Go code (`cmd/`, `internal/`)

- Idiomatic Go; standard library first, third-party only when it's the established choice.
- Table-driven tests; keep functions under the complexity gate; meet the coverage gate.
- `internal/` is the workload that `planner-operator` and `webhook-gateway-operator` deploy —
  changes here ripple into those charms.

## Existing guidance (read, don't duplicate)

- `.github/instructions/` — Copilot-specific: charm-library-update review protocol, code
  commenting style, documentation rules. These are **auto-synced** from upstream
  `canonical/copilot-collections` (pinned in `.copilot-collections.yaml`) by the weekly
  `copilot-collections-update.yml` workflow.
- `CONTRIBUTING.md` — dev workflow, coverage/complexity gates, the 12-factor reference.

### Keeping this file honest

- **Stays in sync with the code** via `scripts/check_agents_md.py` (run in CI by
  `agents_md_check.yaml`): it fails if a cited path, private method, or `tox -e` env no longer
  exists. Cite code by **symbol name**, not line number, so references survive refactors.
- **Stays in sync with copilot-collections**: this file is a hand-curated *adaptation* of the
  upstream guidance (it deliberately diverges for 12-factor — see above), so it can't be
  auto-generated. When the weekly bump PR changes `.copilot-collections.yaml` or
  `.github/instructions/`, re-read the "12-factor divergences" section above (the PR-template
  checklist prompts this).
