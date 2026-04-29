# How to enable log forwarding

The `enable-log-forwarding` action allows workflow authors to opt in to forwarding specific log files from self-hosted GitHub runners to Loki through the OpenTelemetry Collector snap.

By default, nothing is forwarded. Log forwarding starts only when this action is used in a workflow.

## Prerequisites

- Use a self-hosted Linux runner.
- Ensure the workflow can update `/etc/otelcol/config.d` with root privileges.

When this action runs on a GitHub-hosted runner, it performs a no-op and exits successfully so the job can continue.

The action installs `opentelemetry-collector` when it is missing.

## Provide inputs

To enable log forwarding, set the following inputs in your workflow file as required by your setup:

- `files` (required): newline or comma separated file paths or glob patterns.
- `config-file-name` (optional, default `90-github-runner-log-forwarding.yaml`): generated config file name.
- `otlp-endpoint` (optional): OTLP/gRPC endpoint used to create the exporter when one is not already configured.

Avoid adding files that can contain secrets or sensitive information, because forwarded log lines are exported to your telemetry backend.

When `otlp-endpoint` is not set, the action falls back to `ACTION_OTEL_EXPORTER_OTLP_ENDPOINT` from the workflow environment.

## Use the action

Add this snippet to a job in your workflow file (for example, `.github/workflows/ci.yaml`):

```yaml
jobs:
  chrony-testing:
    runs-on: [self-hosted, linux]
    steps:
      - uses: canonical/github-runner-operators/actions/enable-log-forwarding@main
        with:
          files: |
            /var/log/chrony/*.log
            /var/log/syslog
```

Pin the action to a release tag or commit SHA in production workflows.

Use these checks to confirm forwarding:

- Check the action step is completed and prints success messages in the workflow logs.
- Generate new log lines after the action step and query Loki to confirm they arrive.

## Examine Loki queries

The action adds GitHub context as resource attributes on forwarded logs:

- `github.job`
- `github.repository`
- `github.runner`
- `github.workflow`
- `github.run.id`
- `github.run.attempt`

Example Loki query by workflow run id:

```
{github_run_id="123456789"}
```
