# waiting-p80-report

Standalone CLI that extracts the daily P80 of GitHub runner job waiting time from the
planner's PostgreSQL `job` table into a CSV. It is **not** part of the planner charm; no
charm, migration, or metric change is required. Run it from cron, CI, or a laptop.

The waiting time for each job is already stored durably as `started_at - created_at`
(`internal/database/migrations/0001_init.up.sql`), and the `job` table has no TTL, so any past
day's P80 can be recomputed on demand — point the tool at a date range and it recomputes
every day from history.

## Usage

```shell
waiting-p80-report -dsn "$POSTGRESQL_DB_CONNECT_STRING" -from 2026-05-01 -to 2026-05-31 -o p80.csv
```

Flags:

```text
-dsn   PostgreSQL connection string (or POSTGRESQL_DB_CONNECT_STRING env)
-from  start date YYYY-MM-DD (inclusive, UTC)
-to    end date YYYY-MM-DD (inclusive, UTC); defaults to today UTC
-o     output CSV path (default: stdout)
-v     verbose logging to stderr
```

CSV columns: `day,platform,p80_seconds,sample_count`.

The P80 is computed SQL-side via `percentile_cont(0.8) WITHIN GROUP (...)` grouped by the UTC
day the job *started* (the moment waiting ended), matching the population the ephemeral
`github_runner_planner_webhook_job_waiting_seconds` histogram records. Jobs with a NULL
`started_at` or `created_at` are excluded. Days with no started jobs simply do not appear in
the CSV.

## Cron example

Daily at 06:00, appending yesterday's row to a running CSV:

```shell
0 6 * * *  waiting-p80-report -dsn "$DSN" -from $(date -d 'yesterday' +%F) -to $(date -d 'yesterday' +%F) >> /var/log/p80.csv
```

## Testing

- Unit tests (no DB needed): `go test ./cmd/waiting-p80-report/...`
- End-to-end test (requires Postgres): `go test -tags=integration ./cmd/waiting-p80-report/...`
  with `POSTGRESQL_DB_CONNECT_STRING` set. The e2e test is `//go:build integration` tagged,
  mirroring `internal/database/database_test.go`; CI runs it against a `postgres:16.14`
  service container.
