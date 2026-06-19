//go:build integration

// Copyright 2026 Canonical Ltd.
// See LICENSE file for licensing details.

package main

import (
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestReport_EndToEnd seeds jobs with known waiting times into a real Postgres
// (POSTGRESQL_DB_CONNECT_STRING) and asserts the report query returns the
// expected daily P80 and sample_count. Requires -tags=integration and a live DB,
// mirroring the pattern in internal/database/database_test.go.
func TestReport_EndToEnd(t *testing.T) {
	dsn := os.Getenv("POSTGRESQL_DB_CONNECT_STRING")
	if dsn == "" {
		t.Fatal("test database not configured, missing POSTGRESQL_DB_CONNECT_STRING environment variable")
	}

	ctx := t.Context()
	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	defer pool.Close()

	// Reset and create the minimal schema the query needs.
	_, err = pool.Exec(ctx, `
		DROP TABLE IF EXISTS job;
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

	// Seed 5 jobs on 2026-05-01 UTC with waiting times 10,20,30,40,300s.
	// percentile_cont(0.8) over sorted [10,20,30,40,300]: position 0.8*(5-1)=3.2,
	// interpolating between index 3 (40) and index 4 (300): 40 + 0.2*(300-40) = 92.
	day := time.Date(2026, 5, 1, 12, 0, 0, 0, time.UTC)
	waits := []int{10, 20, 30, 40, 300}
	for i, w := range waits {
		created := day.Add(-time.Duration(w) * time.Second)
		_, err = pool.Exec(ctx, `
			INSERT INTO job (platform, id, created_at, started_at, raw)
			VALUES ($1, $2, $3, $4, '{}')`,
			"github", fmt.Sprintf("job-%d", i), created, day)
		require.NoError(t, err)
	}

	// Seed one job on a different day to confirm grouping.
	otherDay := time.Date(2026, 5, 2, 1, 0, 0, 0, time.UTC)
	_, err = pool.Exec(ctx, `
		INSERT INTO job (platform, id, created_at, started_at, raw)
		VALUES ($1, $2, $3, $4, '{}')`,
		"github", "other-day", otherDay.Add(-60*time.Second), otherDay)
	require.NoError(t, err)

	// Seed one job with NULL started_at to confirm it is excluded.
	_, err = pool.Exec(ctx, `
		INSERT INTO job (platform, id, created_at, started_at, raw)
		VALUES ($1, $2, $3, NULL, '{}')`,
		"github", "null-started", day.Add(-999*time.Second))
	require.NoError(t, err)

	cfg := config{
		dsn:  dsn,
		from: time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC),
		to:   time.Date(2026, 5, 3, 0, 0, 0, 0, time.UTC),
	}
	rows, err := queryRows(ctx, cfg)
	require.NoError(t, err)

	require.Len(t, rows, 2, "expected one row per day with started jobs")
	assert.Equal(t, "2026-05-01", rows[0].Day.UTC().Format("2006-01-02"))
	assert.Equal(t, "github", rows[0].Platform)
	assert.Equal(t, 5, rows[0].SampleCount, "NULL-started job must be excluded")
	// P80 interpolates between 40 and 300 -> 92.
	assert.InDelta(t, 92.0, rows[0].P80Seconds, 0.01)

	assert.Equal(t, "2026-05-02", rows[1].Day.UTC().Format("2006-01-02"))
	assert.Equal(t, 1, rows[1].SampleCount)
	assert.InDelta(t, 60.0, rows[1].P80Seconds, 0.01)
}
