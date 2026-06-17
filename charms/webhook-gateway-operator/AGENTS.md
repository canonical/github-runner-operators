# AGENTS.md — webhook-gateway-operator charm

GitHub webhook receiver/forwarder charm. Read the root `AGENTS.md` first; this file lists only
what's specific to `webhook-gateway-operator`.

- **Base: `paas_charm.go.Charm`.** Do **not** add a `_reconcile` method — the base class
  reconciles. The charm's only customisation is overriding `_create_app()` to inject
  OpenTelemetry environment variables; wrap `super()._create_app()`, don't replace it.
- The framework owns the workload — there is no hand-written Pebble layer here. The Go workload
  (HMAC-validate the webhook, forward the job event to the AMQP broker) lives in
  `cmd/webhook-gateway/` + `internal/`.
- Tests: unit in `tests/unit/`; integration via `tox -e webhook-gateway-integration`.
