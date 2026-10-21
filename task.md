Here is a complete, actionable implementation plan for adding automated, per-scaleset OpenStack security group management to the `garm-configurator` and `garm` charms. It is structured so that agent developers can pick up individual tasks and work independently.

---

## 🎯 Objective

Enable the `garm-configurator` charm to reconcile a dedicated, locked-down OpenStack security group for each GitHub scaleset it manages. The charm must create or update the security group to match operator-defined rules, then pass its identifier to the `garm` charm via the existing `garm-configurator` relation. The `garm` charm must consume that identifier and ensure it reaches the `garm-provider-openstack` as the `security_groups` entry in the provider’s `extra_specs` schema.

This keeps responsibility for network‑isolation policy with the configuration layer (the `garm-configurator`) and preserves the `garm` charm as a workload executor that simply forwards configuration to the GARM server and OpenStack provider.

---

## 🗺️ Work Breakdown Structure

### Phase 1 — Foundation & Contracts (Pre‑Implementation)

| Task | Description | Owner | Deliverable |
|------|-------------|-------|-------------|
| **1.1 Define relation‑data contract** | Add a new key `security_group_id` to the `garm-configurator` relation databag. Document it alongside existing keys (`name`, `provider_name`, `image_id`, etc.) in `charms/garm-configurator/src/charm_state.py` and `charms/garm/src/charm_state.py`. | Configurator & GARM charm maintainers | Updated `RUNNER_OPTION_DATABAG_KEYS` or equivalent constant, plus a short design note in `docs/reference/charms.md`. |
| **1.2 Validate OpenStack RBAC** | Confirm that the OpenStack credentials passed to `garm-configurator` (via `openstack-password` secret and related options) already include permissions to create, update, and delete security groups and rules. If not, document the required role (`member` with `create_security_group`, `create_security_group_rule`, `delete_security_group`, `delete_security_group_rule`). | Platform / infra team | A short RFC or issue comment listing the exact OpenStack policy actions. |
| **1.3 Confirm `extra_specs` plumbing** | Verify that the `garm` charm already passes a JSON‑encoded `extra_specs` object to the GARM API when creating a scaleset. If it does not, add an internal function to construct `extra_specs` from relation data. The `garm-provider-openstack` schema already accepts `security_groups` as an array of strings. | GARM charm maintainers | A code comment or unit test proving `extra_specs` can carry `security_groups`. |

**Why first?** These contracts must be agreed upon before parallel work begins on either charm. They also surface any missing OpenStack permissions early, avoiding blocked integration tests later.

---

### Phase 2 — `garm-configurator` Implementation

| Task | Description | Owner | Deliverable |
|------|-------------|-------|-------------|
| **2.1 Add charm configuration options** | Extend `charms/garm-configurator/charmcraft.yaml` with a new option, e.g. `security-group-rules` (type: `string`, JSON‑encoded list of rule objects) and optionally `manage-security-group` (type: `boolean`, default `true`). Document the rule schema in the option description. | Configurator maintainer | Updated `charmcraft.yaml` with new options and validation notes. |
| **2.2 Parse and validate rule configuration** | In `charms/garm-configurator/src/charm_state.py`, add a Pydantic model (e.g. `SecurityGroupRule`) and a validator that parses the `security-group-rules` option. Reject malformed rules with `CharmConfigInvalidError` so the charm enters `BlockedStatus`. | Configurator maintainer | New pydantic model, validation unit tests. |
| **2.3 Implement OpenStack security‑group reconciler** | Create a new module (e.g. `charms/garm-configurator/src/openstack_security_group.py`) with a class `SecurityGroupReconciler`. It must: 1) authenticate using the existing `ProviderConfig` credentials; 2) search for a security group by a deterministic name (e.g. `garm-<scaleset-name>`); 3) create it if missing; 4) diff and reconcile rules (add missing, remove extra); 5) return the security group ID. Use the OpenStack SDK (`openstacksdk`) or `gophercloud`‑style HTTP calls consistent with the charm’s existing dependencies. | Configurator maintainer | A testable reconciler class with idempotent `reconcile()` method. |
| **2.4 Wire reconciler into `_reconcile`** | In `charms/garm-configurator/src/charm.py`, call the reconciler during `_reconcile` (after `CharmState` validation, before `_configure_garm_relation`). If reconciliation fails, set `BlockedStatus` with a clear message; if it succeeds, store the resulting ID on the `CharmState` or pass it directly to `_configure_garm_relation`. | Configurator maintainer | Updated `_reconcile` logic with error handling. |
| **2.5 Publish `security_group_id` to relation** | In `_configure_garm_relation`, add `"security_group_id": <id>` to the `basic_data` dictionary that is written to `relation.data[self.unit]`. Ensure the key is omitted when no security group is managed (backwards compatibility). | Configurator maintainer | Relation databag now includes `security_group_id` when applicable. |
| **2.6 Lifecycle‑safe deletion** | When the charm is removed or the scaleset is deleted, optionally delete the security group **only if** it is not referenced by any other resource. Implement a conservative default: do **not** delete the group automatically unless `manage-security-group` is explicitly set to `true` and a separate `delete-security-group-on-remove` option is enabled. | Configurator maintainer | Safe cleanup logic, documented behaviour. |

**Integration point:** The relation databag currently writes keys such as `name`, `provider_name`, `image_id`, `flavor`, `os_arch`, `min_idle_runner`, `max_runner`, `labels`, `runner_group`, `enable_shell`, and `pre_install_scripts`. Adding `security_group_id` alongside these is a minimal, non‑breaking change.

---

### Phase 3 — `garm` Charm Implementation

| Task | Description | Owner | Deliverable |
|------|-------------|-------|-------------|
| **3.1 Parse `security_group_id` from relation** | In `charms/garm/src/charm_state.py`, add `security_group_id` to the dataclass or mapping that represents a configurator’s scaleset specification. Treat an absent key as `None` so existing deployments continue to work. | GARM charm maintainer | Updated `ScalesetSpec` (or equivalent) with `security_group_id: str \| None`. |
| **3.2 Build `extra_specs` for the provider** | In `charms/garm/src/scaleset_reconciler.py` (or a new helper), construct an `extra_specs` dictionary for the `garm-provider-openstack`. When `security_group_id` is present, include `{"security_groups": [<id>]}`. Pass this dictionary to the GARM API call that creates or updates the scaleset (the `CreateScaleSetParams` model already supports provider‑specific extra specs). | GARM charm maintainer | `extra_specs` populated with `security_groups` when the relation provides an ID. |
| **3.3 Add unit tests** | Extend `charms/garm/tests/unit/` with tests that: 1) a relation databag containing `security_group_id` results in `extra_specs["security_groups"]` being set; 2) an absent key leaves `extra_specs` unchanged. Use the existing pytest‑operator / ops‑testing patterns. | GARM charm maintainer | Passing unit tests covering the new path. |

**Existing code context:** The GARM charm already builds a `ScalesetSpec` dataclass with fields like `name`, `provider_name`, `image`, `flavor`, etc.. Adding `security_group_id` follows the same pattern. The reconciler already calls `self._client.list_providers()` and `self._client.list_scalesets()`, so the API client is in place to accept `extra_specs` in the create/update payload.

---

### Phase 4 — Testing Strategy

| Test Level | Scope | Tools | Deliverable |
|------------|-------|-------|-------------|
| **Unit (configurator)** | Rule parsing, validation errors, reconciler idempotency (create → update → no‑op), relation databag contains `security_group_id`. | `pytest`, `ops.testing`, mocked OpenStack SDK. | ≥ 90 % coverage of new modules. |
| **Unit (GARM charm)** | Relation parsing, `extra_specs` construction, backward compatibility when key is absent. | `pytest`, `ops.testing`. | New test cases in `charms/garm/tests/unit/`. |
| **Integration** | Deploy both charms to a test OpenStack tenant. Configure a scaleset with a locked‑down security group rule (e.g. deny all ingress except GARM callback). Verify that the runner VM is attached to the created security group (via OpenStack CLI: `openstack server show <runner> -f json \| jq '.security_groups'`). Destroy the scaleset and confirm the security group is either left in place (default) or deleted (if opted in). | `pytest-operator`, `tox -e integration` (as per repository `CONTRIBUTING.md`). | A CI‑ready integration test that proves end‑to‑end isolation. |
| **Regression** | Ensure that deployments **without** the new config option continue to work exactly as before (no security group created, no `security_group_id` in relation). | Existing unit + integration suites. | All pre‑existing tests pass unchanged. |

---

### Phase 5 — Documentation & Rollout

| Task | Description | Owner |
|------|-------------|-------|
| **5.1 Update `charmcraft.yaml` descriptions** | Clearly describe the new `security-group-rules` option, its JSON schema, and the isolation benefit. | Configurator maintainer |
| **5.2 Update reference docs** | Add a section to `docs/reference/charms.md` explaining the new relation‑databag key and the security‑group lifecycle. Mention the required OpenStack RBAC. | Documentation maintainer |
| **5.3 Provide an example configuration** | Add a YAML snippet to the tutorial (`docs/tutorial/garm.md`) showing a minimal locked‑down rule set (e.g. allow ingress only from the GARM charm’s IP on port 8080). | Documentation maintainer |
| **5.4 Release notes** | Add a `CHANGELOG.md` entry under “New features” describing automated security‑group reconciliation. Note any permission changes required for existing deployments. | Release manager |
| **5.5 Staged rollout** | Merge behind a feature flag (`manage-security-group` default `false`) so that existing users are unaffected until they explicitly opt in. After one release cycle, consider changing the default to `true` if adoption is smooth. | Platform team |

---

## ⚠️ Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenStack credentials lack `create_security_group_rule` permission. | Configurator enters `BlockedStatus`; runners cannot be isolated. | Pre‑flight validation (Task 1.2) and a clear error message directing operators to add the policy. |
| Security‑group rule conflicts with manually attached groups via `extra_specs`. | Unexpected network behaviour. | Document that the charm‑managed group is **additive**; operators should not duplicate rules in manual `extra_specs`. Provide a `security-group-rules` option that merges rather than replaces. |
| Accidental deletion of a security group still in use. | Running runners lose network access. | Default to **no deletion**; require an explicit `delete-security-group-on-remove` boolean. Before deletion, query OpenStack for ports using the group and refuse if any exist. |
| Backward compatibility broken for existing relation consumers. | Existing `garm` deployments fail to parse the new key. | Omit `security_group_id` when absent; the `garm` charm treats a missing key as `None`. Add a regression test. |

---

## 📦 Deliverables Summary

- **Configurator charm:** New `security-group-rules` (and optional `manage-security-group`) config options; a `SecurityGroupReconciler` module; relation‑databag key `security_group_id`; safe lifecycle handling.
- **GARM charm:** Parsing of `security_group_id`; `extra_specs` construction with `security_groups`; unit tests.
- **Tests:** Unit tests for both charms; an integration test that proves a runner is attached to the expected security group.
- **Docs:** Updated `charmcraft.yaml`, reference documentation, tutorial example, and release notes.
- **Rollout:** Feature flagged with a conservative default, staged promotion through `edge` → `candidate`.

This plan allows agents to work in parallel on the configurator and GARM charm once the Phase 1 contracts are agreed, and it gives each task a concrete, verifiable deliverable.
