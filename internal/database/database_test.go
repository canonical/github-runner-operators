//go:build integration

/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package database

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
)

type testDatabase struct {
	uri string

	conn *pgxpool.Pool
	mu   sync.Mutex
}

func (d *testDatabase) reset(ctx context.Context, conn *pgxpool.Pool) error {
	_, err := conn.Exec(ctx, `
		BEGIN;
		  DROP SCHEMA IF EXISTS public CASCADE;
		  CREATE SCHEMA public;
		
		  GRANT USAGE, CREATE ON SCHEMA public TO PUBLIC;
		  COMMENT ON SCHEMA public IS 'standard public schema';
		COMMIT;`,
	)
	if err != nil {
		return fmt.Errorf("failed to reset database: %v", err)
	}
	return nil
}

func (d *testDatabase) Acquire(ctx context.Context) (*pgxpool.Pool, error) {
	d.mu.Lock()
	conn, err := pgxpool.New(ctx, d.uri)
	if err != nil {
		d.mu.Unlock()
		return nil, fmt.Errorf("failed to connect to the database: %v", err)
	}

	if err := d.reset(ctx, conn); err != nil {
		d.mu.Unlock()
		return nil, err
	}

	err = Migrate(ctx, d.uri)
	if err != nil {
		d.mu.Unlock()
		return nil, err
	}

	d.conn = conn
	return conn, nil
}

func (d *testDatabase) Release(ctx context.Context) error {
	defer d.mu.Unlock()
	d.conn = nil
	return nil
}

var globalTestDatabase *testDatabase

func setupDatabase(t *testing.T) *Database {
	if globalTestDatabase == nil {
		uri, ok := os.LookupEnv("POSTGRESQL_DB_CONNECT_STRING")
		if !ok {
			t.Fatal("test database not configured, missing POSTGRESQL_CONNECT_STRING environment variable")
		}

		globalTestDatabase = &testDatabase{
			uri:  uri,
			conn: nil,
			mu:   sync.Mutex{},
		}
	}

	ctx := t.Context()
	conn, err := globalTestDatabase.Acquire(ctx)
	assert.NoError(t, err)

	return &Database{conn: conn}
}

func teardownDatabase(t *testing.T) {
	if globalTestDatabase != nil {
		assert.NoError(t, globalTestDatabase.Release(t.Context()))
	}
}

func TestDatabase_CreateAuthToken(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	token1, err := db.CreateAuthToken(ctx, "test")
	assert.NoError(t, err)
	token2, err := db.CreateAuthToken(ctx, "foo")
	assert.NoError(t, err)

	assert.NotEqual(t, token1, token2)
}

func TestDatabase_CreateAuthToken_Duplicate(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	_, err := db.CreateAuthToken(ctx, "test")
	assert.NoError(t, err)

	_, err = db.CreateAuthToken(ctx, "test")
	assert.ErrorIs(t, ErrExist, err)

	_, err = db.CreateAuthToken(ctx, "foo")
	assert.NoError(t, err)
}

func TestDatabase_VerifyAuthToken(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	token, err := db.CreateAuthToken(ctx, "foo")
	assert.NoError(t, err)

	name, err := db.VerifyAuthToken(ctx, token)
	assert.NoError(t, err)
	assert.Equal(t, "foo", name)

	token[0] = token[0] + 1
	_, err = db.VerifyAuthToken(ctx, token)
	assert.ErrorIs(t, err, ErrNotExist)
}

func TestDatabase_DeleteAuthToken(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	token, err := db.CreateAuthToken(ctx, "foo")
	assert.NoError(t, err)
	assert.NoError(t, db.DeleteAuthToken(ctx, "foo"))

	_, err = db.VerifyAuthToken(ctx, token)
	assert.ErrorIs(t, err, ErrNotExist)
}

func TestDatabase_AddJob(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}
	assert.NoError(t, db.AddJob(ctx, &job))

	jobs, err := db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)

	assert.Len(t, jobs, 1)
	assert.Equal(t, job, jobs[0])
}

func TestDatabase_AddJob_Exists(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}
	assert.NoError(t, db.AddJob(ctx, &job))
	assert.ErrorIs(t, ErrExist, db.AddJob(ctx, &job))
}

func TestDatabase_AddJob_FlavorSelection(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-medium-ps6",
		Labels:   []string{"self-hosted", "amd64", "medium"},
		Priority: 300,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-large-ps6",
		Labels:   []string{"self-hosted", "amd64", "large"},
		Priority: 200,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-large-ps7",
		Labels:   []string{"self-hosted", "amd64", "large"},
		Priority: 200,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-arm64-large-ps7",
		Labels:   []string{"self-hosted", "arm64", "large"},
		Priority: 150,
	}))

	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "1",
		Labels:   []string{"self-hosted"},
	}))
	jobs, err := db.ListJobs(ctx, "github", ListJobOptions{WithId: "1"})
	assert.NoError(t, err)
	assert.Equal(t, "github-amd64-medium-ps6", *jobs[0].AssignedFlavor)

	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "2",
		Labels:   []string{"self-hosted", "large"},
	}))
	jobs, err = db.ListJobs(ctx, "github", ListJobOptions{WithId: "2"})
	assert.NoError(t, err)
	assert.Contains(t, []string{"github-amd64-large-ps6", "github-amd64-large-ps7"}, *jobs[0].AssignedFlavor)

	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "3",
		Labels:   []string{"self-hosted", "arm64", "large"},
	}))
	jobs, err = db.ListJobs(ctx, "github", ListJobOptions{WithId: "3"})
	assert.NoError(t, err)
	assert.Equal(t, "github-arm64-large-ps7", *jobs[0].AssignedFlavor)

	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "4",
		Labels:   []string{"self-hosted", "s309x", "large"},
	}))
	jobs, err = db.ListJobs(ctx, "github", ListJobOptions{WithId: "4"})
	assert.NoError(t, err)
	assert.Nil(t, jobs[0].AssignedFlavor)
}

func TestDatabase_AddJob_EqualPriority(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-medium-ps6",
		Labels:   []string{"self-hosted", "amd64", "medium"},
		Priority: 300,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-large-ps6",
		Labels:   []string{"self-hosted", "amd64", "large"},
		Priority: 200,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-large-ps7",
		Labels:   []string{"self-hosted", "amd64", "large"},
		Priority: 200,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-arm64-large-ps7",
		Labels:   []string{"self-hosted", "arm64", "large"},
		Priority: 150,
	}))

	for i := range 200 {
		assert.NoError(t, db.AddJob(ctx, &Job{
			Platform: "github",
			ID:       strconv.Itoa(i),
			Labels:   []string{"self-hosted", "amd64", "large"},
		}))
	}

	jobs, err := db.ListJobs(ctx, "github", ListJobOptions{Limit: 200})
	assert.NoError(t, err)

	assignedFlavors := make(map[string]int)

	for _, job := range jobs {
		assignedFlavors[*job.AssignedFlavor]++
	}

	assert.Len(t, assignedFlavors, 2)
	assert.Contains(t, assignedFlavors, "github-amd64-large-ps6")
	assert.Contains(t, assignedFlavors, "github-amd64-large-ps7")
}

func TestDatabase_AddJob_AssignedFlavor(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "amd64-small",
		Labels:   []string{"self-hosted", "amd64", "small"},
		Priority: 0,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "amd64-large",
		Labels:   []string{"self-hosted", "amd64", "large"},
		Priority: 0,
	}))
	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}))

	jobs, err := db.ListJobs(ctx, "github")
	assert.NoError(t, err)

	assert.Len(t, jobs, 1)
	assert.Equal(t, "amd64-large", *jobs[0].AssignedFlavor)
}

func TestDatabase_UpdateJobStarted(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}

	startedAt := time.Date(2025, time.January, 1, 1, 0, 0, 0, time.Local)
	assert.NoError(t, db.AddJob(ctx, &job))
	assert.NoError(t, db.UpdateJobStarted(ctx, job.Platform, job.ID, startedAt, map[string]interface{}{"in_progress": "in_progress"}))

	job.StartedAt = &startedAt
	job.Raw["in_progress"] = "in_progress"

	jobs, err := db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)

	assert.Len(t, jobs, 1)
	assert.Equal(t, job, jobs[0])
}

func TestDatabase_UpdateJobStarted_NotExists(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	err := db.UpdateJobStarted(ctx, "github", "1", time.Date(2025, time.January, 1, 1, 0, 0, 0, time.Local), nil)
	assert.ErrorIs(t, err, ErrNotExist)
}

func TestDatabase_UpdateJobCompleted(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued", "in_progress": "in_progress"},
	}
	startedAt := time.Date(2025, time.January, 1, 1, 0, 0, 0, time.Local)
	job.StartedAt = &startedAt

	completedAt := time.Date(2025, time.January, 1, 2, 0, 0, 0, time.Local)

	assert.NoError(t, db.AddJob(ctx, &job))
	assert.NoError(t, db.UpdateJobCompleted(ctx, job.Platform, job.ID, completedAt, map[string]interface{}{"completed": "completed"}))

	job.CompletedAt = &completedAt
	job.Raw["completed"] = "completed"

	jobs, err := db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)

	assert.Len(t, jobs, 1)
	assert.Equal(t, job, jobs[0])
}

func TestDatabase_UpdateJobCompleted_NotExists(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	err := db.UpdateJobCompleted(ctx, "github", "1", time.Date(2025, time.January, 1, 1, 0, 0, 0, time.Local), nil)
	assert.ErrorIs(t, err, ErrNotExist)
}

func TestDatabase_AddFlavor(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}

	flavor := Flavor{
		Platform:        "github",
		Name:            "amd64-large",
		Labels:          []string{"self-hosted", "amd64", "large"},
		Priority:        0,
		IsDisabled:      false,
		MinimumPressure: 0,
	}

	assert.NoError(t, db.AddJob(ctx, &job))
	assert.NoError(t, db.AddFlavor(ctx, &flavor))

	jobs, err := db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)

	assert.Len(t, jobs, 1)
	assert.Equal(t, flavor.Name, *jobs[0].AssignedFlavor)
}

func TestDatabase_AddFlavor_Exists(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	flavor := Flavor{
		Platform:        "github",
		Name:            "amd64-large",
		Labels:          []string{"self-hosted", "amd64", "large"},
		Priority:        0,
		IsDisabled:      false,
		MinimumPressure: 0,
	}

	assert.NoError(t, db.AddFlavor(ctx, &flavor))
	assert.ErrorIs(t, ErrExist, db.AddFlavor(ctx, &flavor))
}

func TestDatabase_DisableFlavor(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64", "large"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}

	flavor := Flavor{
		Platform:        "github",
		Name:            "amd64-large",
		Labels:          []string{"self-hosted", "amd64", "large"},
		Priority:        0,
		IsDisabled:      false,
		MinimumPressure: 0,
	}

	assert.NoError(t, db.AddJob(ctx, &job))
	assert.NoError(t, db.AddFlavor(ctx, &flavor))
	assert.NoError(t, db.DisableFlavor(ctx, flavor.Platform, flavor.Name))

	jobs, err := db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)
	assert.Nil(t, jobs[0].AssignedFlavor)

	flavors, err := db.ListFlavors(ctx, flavor.Platform)
	assert.NoError(t, err)
	flavor.IsDisabled = true
	assert.Equal(t, []Flavor{flavor}, flavors)
}

func TestDatabase_DisableFlavor_NotExists(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	assert.ErrorIs(t, db.DisableFlavor(ctx, "github", "test"), ErrNotExist)
}

func TestDatabase_DeleteFlavor(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	flavorLarge := Flavor{
		Platform:        "github",
		Name:            "amd64-large",
		Labels:          []string{"self-hosted", "amd64", "large"},
		Priority:        50,
		MinimumPressure: 0,
	}
	flavorSmall := Flavor{
		Platform:        "github",
		Name:            "amd64-small",
		Labels:          []string{"self-hosted", "amd64", "small"},
		Priority:        100,
		MinimumPressure: 0,
	}
	assert.NoError(t, db.AddFlavor(ctx, &flavorLarge))
	assert.NoError(t, db.AddFlavor(ctx, &flavorSmall))

	job := Job{
		Platform:  "github",
		ID:        "1",
		Labels:    []string{"self-hosted", "amd64"},
		CreatedAt: time.Date(2025, time.January, 1, 0, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}
	jobSmall := Job{
		Platform:  "github",
		ID:        "2",
		Labels:    []string{"self-hosted", "amd64", "small"},
		CreatedAt: time.Date(2025, time.January, 1, 1, 0, 0, 0, time.Local),
		Raw:       map[string]interface{}{"queued": "queued"},
	}
	assert.NoError(t, db.AddJob(ctx, &job))
	assert.NoError(t, db.AddJob(ctx, &jobSmall))

	jobs, err := db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)
	assert.Equal(t, flavorSmall.Name, *jobs[0].AssignedFlavor)
	assert.Equal(t, flavorSmall.Name, *jobs[1].AssignedFlavor)

	assert.NoError(t, db.DeleteFlavor(ctx, flavorSmall.Platform, flavorSmall.Name))

	jobs, err = db.ListJobs(ctx, job.Platform)
	assert.NoError(t, err)
	assert.Equal(t, flavorLarge.Name, *jobs[0].AssignedFlavor)
	assert.Nil(t, jobs[1].AssignedFlavor)

	flavors, err := db.ListFlavors(ctx, flavorSmall.Platform)
	assert.NoError(t, err)
	assert.Equal(t, []Flavor{flavorLarge}, flavors)
}

func TestDatabase_ListFlavors(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	flavor1 := Flavor{
		Platform:        "github",
		Name:            "amd64-large",
		Labels:          []string{"self-hosted", "amd64", "large"},
		Priority:        0,
		MinimumPressure: 0,
	}
	flavor2 := Flavor{
		Platform:        "github",
		Name:            "amd64-small",
		Labels:          []string{"self-hosted", "amd64", "small"},
		Priority:        0,
		MinimumPressure: 0,
	}
	assert.NoError(t, db.AddFlavor(ctx, &flavor1))
	assert.NoError(t, db.AddFlavor(ctx, &flavor2))

	flavors, err := db.ListFlavors(ctx, flavor1.Platform)
	assert.NoError(t, err)
	assert.Equal(t, []Flavor{flavor1, flavor2}, flavors)
}

func TestDatabase_GetPressures(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-medium-ps6",
		Labels:   []string{"self-hosted", "amd64", "medium"},
		Priority: 300,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-amd64-large-ps6",
		Labels:   []string{"self-hosted", "amd64", "large"},
		Priority: 200,
	}))
	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform: "github",
		Name:     "github-arm64-large-ps7",
		Labels:   []string{"self-hosted", "arm64", "large"},
		Priority: 150,
	}))

	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "1",
		Labels:   []string{"self-hosted", "amd64", "medium"},
	}))
	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "2",
		Labels:   []string{"self-hosted", "amd64", "large"},
	}))
	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "3",
		Labels:   []string{"self-hosted", "amd64", "large"},
	}))
	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "4",
		Labels:   []string{"self-hosted", "arm64", "large"},
	}))
	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "5",
		Labels:   []string{"self-hosted", "arm64", "large"},
	}))
	assert.NoError(t, db.AddJob(ctx, &Job{
		Platform: "github",
		ID:       "6",
		Labels:   []string{"self-hosted", "arm64", "large"},
	}))

	pressures, err := db.GetPressures(
		ctx,
		"github",
		"github-amd64-medium-ps6",
		"github-amd64-large-ps6",
		"github-arm64-large-ps7",
		"github-s390x-large-ps7",
	)
	assert.NoError(t, err)
	assert.Equal(t, map[string]int{
		"github-amd64-medium-ps6": 1,
		"github-amd64-large-ps6":  2,
		"github-arm64-large-ps7":  3,
		"github-s390x-large-ps7":  0,
	}, pressures)
}

func TestDatabase_GetPressures_MinimumPressure(t *testing.T) {
	db := setupDatabase(t)
	defer teardownDatabase(t)
	ctx := t.Context()

	assert.NoError(t, db.AddFlavor(ctx, &Flavor{
		Platform:        "github",
		Name:            "github-amd64-medium-ps6",
		Labels:          []string{"self-hosted", "amd64", "medium"},
		Priority:        300,
		MinimumPressure: 10,
	}))

	pressures, err := db.GetPressures(ctx, "github", "github-amd64-medium-ps6")
	assert.NoError(t, err)
	assert.Equal(t, 10, pressures["github-amd64-medium-ps6"])
}
