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
| `*-rockcraft.yaml`, `build-*-rock.sh` (repo root) | Rock/image build definitions and their build scripts. |
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
- **Docs spellcheck** — CI runs Vale over `docs/` with `Canonical.000-US-spellcheck` at **error** level, so an unknown technical term (e.g. `deserialize`) fails the build. Add project-specific terms — regex forms like `[Dd]eserializ(e|es|ed|ing|ation)` are supported — to `docs/.custom_wordlist.txt` (the docs `Makefile` appends it to the Canonical accept vocabulary); verify with `make -C docs spellcheck` before pushing a `docs/` change.
- Gates from `CONTRIBUTING.md`: **≥ 85% coverage** on internal packages, **cyclomatic complexity < 10** per function.

## Charm conventions

These are **K8s 12-factor charms** on the `go-framework` charmcraft extension: a thin Python
charm layer wraps a Go workload (`CONTRIBUTING.md` §"12 factor"; each `charmcraft.yaml`).
`garm-configurator` is the exception — a plain `ops` charm.

### Holistic state handling

Read full current state, act idempotently, and set unit status once.

For **`paas_charm` charms** (`garm`, `planner-operator`, `webhook-gateway-operator`) — the base class already runs the holistic flow (`PaasCharm.restart()`):

- **DON'T** implement a separate reconcile — `restart()` already is the reconcile. A thin `_reconcile` dispatcher that just calls `self.restart()` is fine for routing multiple hook observers through one entry point; a `_reconcile` that implements its own reconcile logic is not.
- **DO** inject behaviour by overriding a framework hook and calling `super()` — e.g. `restart()` (`garm`: write config + first-run; `planner-operator`: sync relation endpoints) or `_create_app()` (`planner-operator`/`webhook-gateway-operator`: inject OTel env).
- **DO** gate on readiness with an early return (`if not self.is_ready(): return`); **DON'T** call `event.defer()`.

For **`garm-configurator`** (plain `ops`):

- **DO** keep the single `_reconcile` that every event observes (`GarmConfiguratorCharm._reconcile`): build state via `CharmState.from_charm(self)`, write relation data, set status once at the end.

### Ops / Juju lifecycle idioms to take care of

- **Secrets — owner vs observer.** `refresh=True` is an *observer* concept: it advances the unit's *tracked* revision to the latest.
  - **DO** pass `get_content(refresh=True)` only when **consuming a secret you don't own** (an operator-supplied config secret, or one granted over a relation), especially in `secret-changed` handlers — e.g. the `*.from_charm` resolvers in `charms/garm-configurator/src/charm_state.py`.
  - **DON'T** pass `refresh=True` for a secret you **own** (created via `add_secret`): plain `get_content()` already returns the latest revision and `set_content()` invalidates the cache — e.g. `garm`'s `_get_secrets` / `_get_admin_credentials`. Use `peek_content()` to read the latest without changing tracking.
  - **DO** create labelled secrets on the leader so other units can fetch them by `label`.
- **DO** put the secret id/URI in relation data; **DON'T** put the content: `add_secret(..., label=...)` → `secret.grant(relation)` → `relation.data[self.app]["token"] = str(secret.id)` (`planner-operator`'s `_create_relation_credentials`).
- **DO** serialise structured values (e.g. `json.dumps`) — relation databags are string-only.

### Testing

- New unit tests use **Scenario** (`scenario.Context` / `State` / `Relation` / `Secret`),
  not `Harness` — see `charms/garm-configurator/tests/unit/`.
- Integration tests live in the shared `charms/tests/integration/`.

## 12-factor divergences from the canonical charm-engineer guidance

We borrow from the canonical
[`charm-engineer.agent.md`](https://github.com/canonical/copilot-collections/blob/main/groups/platform-engineering/agents/charm-engineer.agent.md),
but some of its rules assume a hand-written `ops` charm and do **not** apply to our paas charms:

- **No separate reconcile logic** — `restart()` is the reconcile (see above). A thin `_reconcile` dispatcher that just calls `self.restart()` is fine; don't implement reconcile logic outside `restart()`.
- **No hand-authored `workload.py` / Pebble layer** — the `go-framework` extension owns the
  workload; touch Pebble only inside a `restart()` override when strictly necessary.
- **A `CharmState` abstraction is optional but encouraged where it cuts `charm.py` complexity**
  (per [ISD014](https://discourse.charmhub.io/t/specification-isd014-managing-charm-complexity/11619)).
  `garm-configurator` uses a Pydantic `CharmState`; `garm` uses a `dataclasses`-based
  `charm_state.py` (`CharmState.from_charm`) for relation-derived desired state. Don't force one
  onto a trivial paas charm, and keep it dependency-free of `charm.py` (no import cycle).

Still applicable: holistic state handling, idempotent `install`, explicit port handling, small
`try/except` blocks scoped to custom exceptions, no Canonical-internal references in charm
code, and **avoid `level=alive` health checks** in `rockcraft.yaml`.

## Go code (`cmd/`, `internal/`)

- Idiomatic Go; standard library first, third-party only when it's the established choice.
- Table-driven tests; keep functions under the complexity gate; meet the coverage gate.
- `internal/` is the workload that `planner-operator` and `webhook-gateway-operator` deploy —
  changes here ripple into those charms.

## Existing guidance (read, don't duplicate)

- `.github/instructions/` — guidance in GitHub Copilot's custom-instructions format
  (`applyTo` frontmatter), **auto-synced** from upstream `canonical/copilot-collections`
  (pinned in `.copilot-collections.yaml`) by the weekly `copilot-collections-update.yml`
  workflow. The format/delivery is Copilot-specific, but most of the content
  (code-commenting style, documentation rules, the charm-library-update review protocol) is
  general guidance worth following regardless of tool.
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
