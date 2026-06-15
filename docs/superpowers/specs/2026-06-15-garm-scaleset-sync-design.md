# Design: GARM Scaleset Sync via REST API (ISD-5729)

**Date:** 2026-06-15
**Story:** ISD-5729 — Sync scalesets via GARM REST API without service restart
**Status:** Approved

## Context

The GARM charm manages the GARM service (GitHub Actions Runner Manager) as a 12-factor K8S
charm. Configurator charms each represent one scaleset+provider combination and share their
configuration with GARM via Juju relations.

This story wires the two charms together: the GARM charm reads desired scaleset state from
all connected Configurator relations, diffs it against the live GARM REST API state, and
applies the minimum set of create/update/delete operations. No service restart is needed.
Providers (story #8) and credentials (story #9) are pre-existing concerns; this story defers
gracefully when they are absent.

## Architecture

```
garm-configurator (N) ──garm_configurator_v0──► garm charm
                                                     │
                                              GarmClient (garm_api.py)
                                                     │
                                          ScalesetReconciler (scaleset_reconciler.py)
                                                     │
                                         GARM REST API :9997
```

The Configurator charm is a pure config-broker with no workload. The GARM charm is the sole
consumer of the relation data and the sole caller of the GARM REST API.

## Components

### 1. Relation interface — `garm_configurator_v0`

**`garm-configurator/charmcraft.yaml`** gains:

```yaml
provides:
  garm-configurator:
    interface: garm_configurator_v0
```

**`garm/charmcraft.yaml`** gains:

```yaml
requires:
  garm-configurator:
    interface: garm_configurator_v0
```

**Databag keys** written by the Configurator unit:

| Key | Type | Notes |
|-----|------|-------|
| `name` | str | Scaleset name |
| `provider_name` | str | Computed as `openstack-{project_name}` |
| `credentials_name` | str | Computed as `github-app-{client_id}` |
| `image_id` | str | OpenStack image UUID from image builder |
| `flavor` | str | OpenStack flavor |
| `os_arch` | str | CPU architecture, e.g. `amd64` |
| `min_idle_runner` | str | Integer serialised as string |
| `max_runner` | str | Integer serialised as string |
| `labels` | str | Comma-separated label list |
| `repo` | str | Repository target (empty string if absent) |
| `org` | str | Org target (empty string if absent) |
| `runner_group` | str | Runner group, default `"default"` |
| `pre_install_scripts` | str | Pre-install script content (empty if absent) |

The Configurator only writes the databag when `image_id` is available (i.e. after the image
builder relation delivers a UUID). GARM ignores units with an empty `image_id`.

### 2. GARM REST API authentication

`garm-secrets` gains two new fields: `admin-username` (always `"admin"`) and `admin-password`
(strong random: uppercase, lowercase, digit, symbol — generated once by the leader on
install). `_generate_garm_secrets()` is updated accordingly.

On each reconcile pass the GARM charm:

1. Checks that the Pebble `app` service is running — returns early if not.
2. Calls `POST /api/v1/first-run` (idempotent: `200` = initialised now, `409` = already done).
3. Calls `PUT /api/v1/controller` to set `metadata_url`, `callback_url`, `webhook_url` (idempotent).
4. Calls `POST /api/v1/auth/login` → short-lived JWT used for all subsequent calls.
5. `GarmApiError` at any step is caught at the reconcile boundary, logged, and exits cleanly
   — no error state is set.

### 3. `garm_api.py` — GARM REST client

A new file `charms/garm/src/garm_api.py`. Uses `urllib.request` (no new runtime dependencies).

Key public surface:

```python
class GarmApiError(Exception): ...

class GarmClient:
    def __init__(self, base_url: str) -> None: ...
    def first_run(self, username: str, password: str, email: str, full_name: str) -> None: ...
    def configure_controller(self, metadata_url: str, callback_url: str, webhook_url: str) -> None: ...
    def login(self, username: str, password: str) -> str:  # returns JWT ...
    def list_providers(self) -> list[dict]: ...
    def list_credentials(self) -> list[dict]: ...
    def list_scalesets(self) -> list[dict]: ...
    def create_scaleset(self, payload: dict) -> dict: ...
    def update_scaleset(self, scaleset_id: str, payload: dict) -> dict: ...
    def delete_scaleset(self, scaleset_id: str) -> None: ...
```

All methods require a JWT (set via `client.token = jwt_string`), except `first_run` and `login`.

### 4. `scaleset_reconciler.py` — pure diff logic

A new file `charms/garm/src/scaleset_reconciler.py`. No `ops` imports — fully unit-testable
without a Juju context.

```python
@dataclass
class DesiredScaleset:
    name: str
    provider_name: str
    credentials_name: str
    image_id: str
    flavor: str
    os_arch: str
    min_idle_runner: int
    max_runner: int
    labels: str
    repo: str
    org: str
    runner_group: str
    pre_install_scripts: str

@dataclass
class ReconcileResult:
    created: list[str]
    updated: list[str]
    deleted: list[str]
    skipped: list[str]  # missing provider or credential

class ScalesetReconciler:
    def __init__(self, client: GarmClient) -> None: ...
    def reconcile(self, desired: list[DesiredScaleset]) -> ReconcileResult: ...
```

**Reconcile algorithm:**

1. `GET /api/v1/scalesets` → `observed` dict keyed by scaleset `name`.
2. `GET /api/v1/providers` → set of known provider names.
3. `GET /api/v1/credentials` → set of known credential names.
4. For each desired scaleset:
   - `provider_name` not in providers → log warning, add to `skipped`, continue.
   - `credentials_name` not in credentials → log warning, add to `skipped`, continue.
   - Not in `observed` → `POST /api/v1/scalesets` (create), add to `created`.
   - In `observed` and at least one field differs → `PUT /api/v1/scalesets/{id}` (update), add to `updated`.
   - Otherwise → no-op.
5. For each observed scaleset whose `name` is **not** in desired → `DELETE /api/v1/scalesets/{id}`, add to `deleted`.

The reconciler treats all scalesets returned by GARM as charm-owned. Operators must not
manually create scalesets in GARM when the charm is active, as the reconciler will delete
any scaleset not present in the desired set. Scaleset names are expected to be globally unique
across all connected Configurator instances.

### 5. GARM charm changes (`charm.py`)

New observed events in `GarmCharm.__init__`:

```python
for event in [
    self.on["garm-configurator"].relation_joined,
    self.on["garm-configurator"].relation_changed,
    self.on["garm-configurator"].relation_broken,
]:
    self.framework.observe(event, self._on_configurator_changed)
```

`_on_configurator_changed` builds the `desired` list from all `garm-configurator` relation
units, then calls `_reconcile_scalesets(desired)`. Units with empty `image_id` are skipped.

`_reconcile_scalesets(desired)`:
1. Acquires JWT (first-run + login flow via `GarmClient`).
2. Calls `ScalesetReconciler(client).reconcile(desired)`.
3. Logs result; does not alter unit status — status is owned by the parent restart/config flow.

`_generate_garm_secrets()` gains `admin-username` and `admin-password` keys.

### 6. Configurator charm changes (`charm.py` and `charm_state.py`)

`charm_state.py` adds two computed properties to `CharmState`:

- `provider_name: str` — `f"openstack-{self.provider_config.project_name}"`
- `credentials_name: str` — `f"github-app-{self.github_app_config.client_id}"`

`charm.py` `_reconcile()` additionally writes to the `garm-configurator` relation databag
(iterating over all `garm-configurator` relations) when `state.image_id` is not None.

## Error handling and deferral

| Condition | Behaviour |
|-----------|-----------|
| Pebble service not running | Return early from reconcile; no status change |
| `GarmApiError` (network, auth, server error) | Log warning, return; unit stays at current status |
| Provider not found in GARM | Skip that scaleset; log warning; process others |
| Credential not found in GARM | Skip that scaleset; log warning; process others |
| `image_id` empty in relation databag | Skip that unit; others are processed |

No event is deferred (ops.EventBase.defer()). The next relation-changed or config-changed
event will re-trigger reconcile cleanly.

## Testing

### Unit tests (new files)

- `charms/garm/tests/unit/test_garm_api.py` — tests `GarmClient` with mock HTTP responses
- `charms/garm/tests/unit/test_scaleset_reconciler.py` — tests reconcile diff logic
  with a stub `GarmClient`
- `charms/garm/tests/unit/test_charm.py` — tests `_on_configurator_changed` using
  `ops.testing.Context/State`

### Integration tests (additions to `test_garm.py`)

| Test | Asserts |
|------|---------|
| `test_scaleset_created` | Scaleset appears in `GET /api/v1/scalesets` after integrating configurator |
| `test_scaleset_updated` | Scaleset fields updated after changing configurator config (no restart) |
| `test_scaleset_deleted` | Scaleset removed after removing the relation |
| `test_scaleset_deferred_missing_credential` | No scaleset created; unit Active/Waiting; no error state |

Tests reuse `garm_app`, `postgresql`, `any_charm_image_builder_app` fixtures. The
`garm_configurator_app` fixture from `test_garm_configurator.py` is extracted to the shared
`conftest.py` so both test modules can use it.

## Constraints and non-goals

- This story does **not** create GARM providers (story #8) or credentials (story #9) — it only
  reads them to check existence.
- No service restart is triggered for any scaleset change.
- The reconcile is idempotent: running it twice with the same desired state produces no API
  calls on the second run.
