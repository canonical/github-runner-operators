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
-dsn        PostgreSQL connection string (or POSTGRESQL_DB_CONNECT_STRING env)
-from       start date YYYY-MM-DD (inclusive, UTC)
-to         end date YYYY-MM-DD (inclusive, UTC); defaults to today UTC
-o          output CSV path (default: stdout)
-v          verbose logging to stderr
-no-header  omit CSV header line (useful for appending to an existing CSV)
```

CSV columns: `day,platform,p80_seconds,sample_count`.

The P80 is computed SQL-side via `percentile_cont(0.8) WITHIN GROUP (...)` grouped by the UTC
day the job *started* (the moment waiting ended), matching the population the ephemeral
`github_runner_planner_webhook_job_waiting_seconds` histogram records. Jobs with a NULL
`started_at` or `created_at` are excluded. Rows where `started_at < created_at` (negative
waiting times from clock skew, for jobs that effectively started immediately) are clamped to
0 rather than dropped — keeping them in the population avoids biasing the percentile upward
and matches how the histogram buckets them. Days with no started jobs simply do not appear in
the CSV.

Only jobs **we own** are counted: the query filters on `assigned_flavor IS NOT NULL`, which is
set when a job's labels match one of our configured flavors. Jobs served by runners we
don't manage (for example, third-party self-hosted runners on repositories we ingest webhooks
from, such as `spread-enabled`) never match a flavor and are excluded so they don't skew the P80.

> **Caveat — data before 2026-06-18.** Case-insensitive label matching landed then
> (`fix(planner): match runner labels case-insensitively`, #243; see the 2026-06-18 changelog
> entry). Its migration re-ran flavor assignment only for *in-progress* jobs; **completed** jobs
> that we owned but that missed assignment due to label casing (for example, job label `X64` not
> matching flavor `x64`) were left at `assigned_flavor = NULL` and never backfilled. For day
> ranges before 2026-06-18 those jobs are therefore excluded, so `sample_count` is lower than the
> true total and the P80 may be skewed. Reports over ranges from 2026-06-18 onward are unaffected.

## Cron example

Daily at 06:00, appending yesterday's row to a running CSV (use `-no-header` so the header
is not repeated on each append):

```shell
0 6 * * *  waiting-p80-report -dsn "$DSN" -no-header -from $(date -d 'yesterday' +%F) -to $(date -d 'yesterday' +%F) >> /var/log/p80.csv
```

## Testing

- Unit tests (no DB needed): `go test ./cmd/waiting-p80-report/...`
- End-to-end test (requires Postgres): `go test -tags=integration ./cmd/waiting-p80-report/...`
  with `POSTGRESQL_DB_CONNECT_STRING` set. The e2e test is `//go:build integration` tagged,
  mirroring `internal/database/database_test.go`; CI runs it against a `postgres:16.14`
  service container.
