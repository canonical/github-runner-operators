//go:build integration

// Copyright 2026 Canonical Ltd.
// See LICENSE file for licensing details.

package main

import (
	"fmt"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// testSchema is a dedicated schema for e2e test isolation, so this test does not
// mutate the shared public schema used by internal/database integration tests
// when packages run in parallel.
const testSchema = "waiting_p80_e2e"

// withSearchPath returns a copy of dsn with search_path set to the given schema
// via the libpq options parameter, so all connections from that DSN resolve
// unqualified table names against the isolated schema.
func withSearchPath(t *testing.T, dsn, schema string) string {
	t.Helper()
	u, err := url.Parse(dsn)
	require.NoError(t, err)
	q := u.Query()
	q.Set("options", "-c search_path="+schema)
	u.RawQuery = q.Encode()
	return u.String()
}

// TestReport_EndToEnd seeds jobs with known waiting times into a real Postgres
// (POSTGRESQL_DB_CONNECT_STRING) using an isolated schema and asserts the
// report query returns the expected daily P80 and sample_count. Requires
// -tags=integration and a live DB, mirroring the pattern in
// internal/database/database_test.go.
func TestReport_EndToEnd(t *testing.T) {
	dsn := os.Getenv("POSTGRESQL_DB_CONNECT_STRING")
	if dsn == "" {
		t.Fatal("test database not configured, missing POSTGRESQL_DB_CONNECT_STRING environment variable")
	}

	isolatedDSN := withSearchPath(t, dsn, testSchema)

	ctx := t.Context()
	pool, err := pgxpool.New(ctx, isolatedDSN)
	require.NoError(t, err)
	defer pool.Close()

	// Create an isolated schema so this test does not clash with other
	// integration test packages that reset the public schema.
	_, err = pool.Exec(ctx, fmt.Sprintf(`
		DROP SCHEMA IF EXISTS %s CASCADE;
		CREATE SCHEMA %s;`, testSchema, testSchema))
	require.NoError(t, err)
	t.Cleanup(func() {
		_, _ = pool.Exec(ctx, fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", testSchema))
	})

	// Create the minimal table the query needs, inside the isolated schema.
	_, err = pool.Exec(ctx, `
		CREATE TABLE job (
			pk              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
			platform        TEXT        NOT NULL,
			id              TEXT        NOT NULL,
			labels          TEXT[]      NOT NULL DEFAULT '{}',
			created_at      TIMESTAMPTZ NOT NULL,
			started_at      TIMESTAMPTZ,
			completed_at    TIMESTAMPTZ,
			raw             JSONB       NOT NULL DEFAULT '{}',
			assigned_flavor TEXT,
			UNIQUE (platform, id),
			CHECK (platform <> '' AND id <> '')
		);`)
	require.NoError(t, err)

	// Seed 5 owned jobs on 2026-05-01 UTC with waiting times 10,20,30,40,300s.
	// Each carries an assigned_flavor because the report counts only jobs we
	// own (those whose labels matched one of our flavors). Over these 5 alone,
	// percentile_cont(0.8) of sorted [10,20,30,40,300] is 40 + 0.2*(300-40) = 92
	// (position 0.8*(5-1)=3.2). A negative-wait job seeded below joins this day's
	// population, so the asserted day-1 P80 is 40, not 92 — see the assertion.
	day := time.Date(2026, 5, 1, 12, 0, 0, 0, time.UTC)
	waits := []int{10, 20, 30, 40, 300}
	for i, w := range waits {
		created := day.Add(-time.Duration(w) * time.Second)
		_, err = pool.Exec(ctx, `
			INSERT INTO job (platform, id, created_at, started_at, raw, assigned_flavor)
			VALUES ($1, $2, $3, $4, '{}', 'small')`,
			"github", fmt.Sprintf("job-%d", i), created, day)
		require.NoError(t, err)
	}

	// Seed one job on a different day to confirm grouping.
	otherDay := time.Date(2026, 5, 2, 1, 0, 0, 0, time.UTC)
	_, err = pool.Exec(ctx, `
		INSERT INTO job (platform, id, created_at, started_at, raw, assigned_flavor)
		VALUES ($1, $2, $3, $4, '{}', 'small')`,
		"github", "other-day", otherDay.Add(-60*time.Second), otherDay)
	require.NoError(t, err)

	// Seed one job with NULL started_at to confirm it is excluded.
	_, err = pool.Exec(ctx, `
		INSERT INTO job (platform, id, created_at, started_at, raw, assigned_flavor)
		VALUES ($1, $2, $3, NULL, '{}', 'small')`,
		"github", "null-started", day.Add(-999*time.Second))
	require.NoError(t, err)

	// Seed one job where started_at < created_at (negative wait, -10s) to
	// confirm it is clamped to 0 and kept in the population, not excluded.
	_, err = pool.Exec(ctx, `
		INSERT INTO job (platform, id, created_at, started_at, raw, assigned_flavor)
		VALUES ($1, $2, $3, $4, '{}', 'small')`,
		"github", "negative-wait", day.Add(10*time.Second), day)
	require.NoError(t, err)

	// Seed one job we don't own (NULL assigned_flavor) on day 1 with an
	// otherwise-valid 50s wait, to confirm it is excluded from the P80 and the
	// sample count. Without the assigned_flavor filter this would push day-1 to
	// 7 samples and skew the percentile.
	_, err = pool.Exec(ctx, `
		INSERT INTO job (platform, id, created_at, started_at, raw)
		VALUES ($1, $2, $3, $4, '{}')`,
		"github", "unowned", day.Add(-50*time.Second), day)
	require.NoError(t, err)

	cfg := config{
		dsn:  isolatedDSN,
		from: time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC),
		to:   time.Date(2026, 5, 3, 0, 0, 0, 0, time.UTC),
	}
	rows, err := queryRows(ctx, cfg)
	require.NoError(t, err)

	require.Len(t, rows, 2, "expected one row per day with started jobs")
	assert.Equal(t, "2026-05-01", rows[0].Day.UTC().Format("2006-01-02"))
	assert.Equal(t, "github", rows[0].Platform)
	assert.Equal(t, int64(6), rows[0].SampleCount, "NULL-started and unowned (NULL flavor) excluded; negative-wait clamped to 0 and kept")
	// The negative-wait job is clamped to 0, so the day-1 population is sorted
	// [0,10,20,30,40,300] (n=6). percentile_cont(0.8) position 0.8*(6-1)=4.0
	// lands exactly on index 4 -> 40.
	assert.InDelta(t, 40.0, rows[0].P80Seconds, 0.01)

	assert.Equal(t, "2026-05-02", rows[1].Day.UTC().Format("2006-01-02"))
	assert.Equal(t, int64(1), rows[1].SampleCount)
	assert.InDelta(t, 60.0, rows[1].P80Seconds, 0.01)
}
