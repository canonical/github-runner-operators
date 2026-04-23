# Enable log forwarding

The `enable-log-forwarding` action allows workflow authors to opt in to forwarding specific log files from self-hosted GitHub runners to Loki through the OpenTelemetry Collector snap.

By default, nothing is forwarded. Log forwarding starts only when this action is used in a workflow.

## Inputs

- `files` (required): newline or comma separated file paths or glob patterns.
- `config-file-name` (optional, default `90-github-runner-log-forwarding.yaml`): generated config file name.
- `otlp-endpoint` (optional): OTLP/HTTP endpoint used to create the exporter when one is not already configured.

When `otlp-endpoint` is not set, the action falls back to `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT` from the workflow environment.

## Usage

```yaml
jobs:
  chrony-testing:
    runs-on: ubuntu-latest
    steps:
      - uses: canonical/github-runner-operators/actions/enable-log-forwarding@main
        with:
          files: |
            /var/log/chrony/*.log
            /var/log/syslog
      - run: ./run-tests.sh
```

Pin to a release tag or commit SHA in production workflows.

## Loki query hints

The action adds GitHub context as resource attributes on forwarded logs:

- `github.job.id`
- `github.job.name`
- `github.repository`
- `github.runner.name`
- `github.workflow`
- `github.run.attempt`

Example Loki query by workflow run id:

```logql
{github_job_id="123456789"}
```

## Notes

- This action requires root privileges to write collector config.
- The `opentelemetry-collector` snap must be installed on the runner.
