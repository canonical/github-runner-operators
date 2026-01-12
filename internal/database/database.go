/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

// Package database provides persistent storage for auth tokens, jobs, and flavors,
// and computes "pressure" for each flavor.
//
// Pressure is a numeric measure of demand for runner machines (flavors). It is
// defined as the number of incomplete jobs (completed_at IS NULL) assigned to a
// given flavor.
//
// When a job is inserted, it is assigned a flavor using the following algorithm:
//  1. The flavor's platform must match the job's platform.
//  2. The flavor's labels must be a superset of (or equal to) the job's labels.
//  3. If multiple flavors match, choose the one with the highest priority.
//  4. If there is still a tie, pick one at random.
package database

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	DefaultLimit              = 100
	channelBufferSize         = 16
	pressureChangeChannelName = `pressure_change`
	pressureChangeSql         = `NOTIFY ` + pressureChangeChannelName + `;`
	updateAssignedFlavorSql   = `
	UPDATE job AS j
	SET assigned_flavor = (SELECT f.name
						   FROM flavor AS f
						   WHERE f.is_disabled = FALSE
							 AND f.platform = j.platform
							 AND f.labels @> j.labels
						   ORDER BY f.priority DESC, random()
						   LIMIT 1)
	WHERE j.assigned_flavor IS NULL AND j.completed_at IS NULL
	  AND EXISTS (SELECT 1
				  FROM flavor AS f
				  WHERE f.is_disabled = FALSE
					AND f.platform = j.platform
					AND f.labels @> j.labels
				  );
`
)

var (
	ErrNotExist = errors.New("does not exist")
	ErrExist    = errors.New("already exists")
)

type Database struct {
	conn *pgxpool.Pool
}

type ListJobOptions struct {
	WithId           string
	OnlyNotCompleted bool
	CreatedAfter     time.Time
	Limit            int
}

type DatabaseEventListener struct {
	// pgx.Conn is used, since pgxpool.Pool.Conn does not support LISTEN/NOTIFY.
	conn *pgx.Conn
}

// CreateAuthToken creates an authentication token for the given name.
// If a token with the same name already exists, it returns ErrExist.
// The returned token is a 256-bit random byte slice and can be verified
// with VerifyAuthToken.
func (d *Database) CreateAuthToken(ctx context.Context, name string) ([32]byte, error) {
	token := [32]byte{}
	_, err := rand.Read(token[:])
	if err != nil {
		return token, fmt.Errorf("failed to generate token: %w", err)
	}
	sha := sha256.New()
	sha.Write(token[:])
	hash := hex.EncodeToString(sha.Sum(nil))
	tag, err := d.conn.Exec(ctx, "INSERT INTO auth (name, token) VALUES ($1, $2) ON CONFLICT (name) DO NOTHING;\n", name, hash)
	if err != nil {
		return token, fmt.Errorf("failed to insert auth token: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return token, ErrExist
	}
	return token, nil
}

// VerifyAuthToken verifies an authentication token.
// It returns the associated token name if the token is valid.
// If the token is invalid or not found, it returns ErrNotExist.
func (d *Database) VerifyAuthToken(ctx context.Context, token [32]byte) (string, error) {
	sha := sha256.New()
	sha.Write(token[:])
	hash := hex.EncodeToString(sha.Sum(nil))

	var name string
	row := d.conn.QueryRow(ctx, "SELECT name FROM auth WHERE token = $1", hash)
	if err := row.Scan(&name); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", ErrNotExist
		}
		return "", fmt.Errorf("failed to get auth name: %w", err)
	}
	return name, nil
}

// DeleteAuthToken deletes an authentication token.
// If the token doesn't exist, DeleteAuthToken does nothing.
func (d *Database) DeleteAuthToken(ctx context.Context, name string) error {
	_, err := d.conn.Exec(ctx, "DELETE FROM auth WHERE name = $1", name)
	if err != nil {
		return fmt.Errorf("failed to delete auth token: %w", err)
	}
	return nil
}

// AddJob inserts a job into the database.
// All fields from job are persisted except AssignedFlavor, which is computed
// by the flavor-assignment (pressure) algorithm.
// If a job with the same (platform, id) already exists, it returns ErrExist.
func (d *Database) AddJob(ctx context.Context, job *Job) error {
	const stmt = `
	INSERT INTO job (
	  platform, id, labels, created_at, started_at, completed_at, raw, assigned_flavor
	)
	SELECT
	  @platform, @id, @labels, @created_at, @started_at, @completed_at, @raw,
	  CASE
		WHEN @completed_at::timestamptz IS NULL THEN (
		  SELECT f.name
		  FROM flavor AS f
		  WHERE f.is_disabled = FALSE
			AND f.platform = @platform
			AND f.labels @> @labels
		  ORDER BY f.priority DESC, random()
		  LIMIT 1
		)
		ELSE NULL
	  END
	ON CONFLICT (platform, id) DO NOTHING;
	`

	raw := job.Raw
	if raw == nil {
		raw = map[string]interface{}{}
	}

	batch := &pgx.Batch{}
	batch.Queue(
		stmt,
		pgx.NamedArgs{
			"platform":     job.Platform,
			"id":           job.ID,
			"labels":       job.Labels,
			"created_at":   job.CreatedAt,
			"started_at":   job.StartedAt,
			"completed_at": job.CompletedAt,
			"raw":          raw,
		})
	batch.Queue(pressureChangeSql)
	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for inserting job", "error", err)
		}
	}()

	for i := range batch.Len() {
		tag, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to insert job: %w", err)
		}
		if i == 0 && tag.RowsAffected() == 0 {
			return ErrExist
		}
	}
	return nil
}

func (d *Database) createListJobsSqlArgs(platform string, options ListJobOptions) (string, pgx.NamedArgs) {
	sql := `
	SELECT
	  platform,
	  id,
	  labels,
	  created_at,
	  started_at,
	  completed_at,
	  raw,
	  assigned_flavor
	FROM job
	WHERE platform = @platform
	`
	args := pgx.NamedArgs{"platform": platform}
	if options.WithId != "" {
		sql += "\nAND id = @id"
		args["id"] = options.WithId
	}

	if options.OnlyNotCompleted {
		sql += "\nAND completed_at IS NULL"
	}

	if !options.CreatedAfter.IsZero() {
		sql += "\nAND created_at > @created_at"
		args["created_at"] = options.CreatedAfter
	}

	limit := options.Limit
	if limit == 0 {
		limit = DefaultLimit
	}

	sql += "\n ORDER BY created_at LIMIT @limit"
	args["limit"] = limit
	return sql, args
}

// ListJobs returns stored jobs.
// Use ListJobOptions to filter results. If ListJobOptions.Limit is 0,
// DefaultLimit is applied.
func (d *Database) ListJobs(ctx context.Context, platform string, option ...ListJobOptions) ([]Job, error) {
	opt := ListJobOptions{}
	if len(option) > 0 {
		opt = option[0]
	}
	sql, args := d.createListJobsSqlArgs(platform, opt)
	rows, err := d.conn.Query(ctx, sql, args)
	if err != nil {
		return nil, fmt.Errorf("failed to list jobs: %w", err)
	}
	jobs, err := pgx.CollectRows[Job](rows, pgx.RowToStructByName)
	if err != nil {
		return nil, fmt.Errorf("failed to list jobs: %w", err)
	}
	return jobs, nil
}

// UpdateJobStarted updates a job's started_at field.
// If raw is provided, it is merged into the existing raw payload in the database.
// If the job doesn't exist, it will return ErrNotExist.
func (d *Database) UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]interface{}) error {
	const sql = `
		UPDATE job
		SET
			started_at = @started_at,
			raw = COALESCE(job.raw, '{}'::jsonb) || COALESCE(@raw::jsonb, '{}'::jsonb)
		WHERE platform = @platform AND id = @id;
	`

	tag, err := d.conn.Exec(ctx, sql, pgx.NamedArgs{
		"platform":   platform,
		"id":         id,
		"started_at": startedAt,
		"raw":        raw,
	})
	if err != nil {
		return fmt.Errorf("failed to update job started_at time: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotExist
	}
	return nil
}

// UpdateJobCompleted updates a job's completed_at field.
// If raw is provided, it is merged into the existing raw payload in the database.
// If the job doesn't exist, it will return ErrNotExist.
func (d *Database) UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]interface{}) error {
	const stmt = `
		UPDATE job
		SET
			completed_at = @completed_at,
			raw = COALESCE(job.raw, '{}'::jsonb) || COALESCE(@raw::jsonb, '{}'::jsonb)
		WHERE platform = @platform AND id = @id;
	`

	batch := &pgx.Batch{}
	batch.Queue(
		stmt,
		pgx.NamedArgs{
			"platform":     platform,
			"id":           id,
			"completed_at": completedAt,
			"raw":          raw,
		})
	batch.Queue(pressureChangeSql)
	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for updating job completed_at time", "error", err)
		}
	}()

	for i := range batch.Len() {
		tag, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to update job completed_at time: %w", err)
		}
		if i == 0 && tag.RowsAffected() == 0 {
			return ErrNotExist
		}
	}
	return nil
}

// AddFlavor inserts a new flavor into the database.
// Returns ErrExist if a flavor with the same name already exists.
// After insertion, the flavor-assignment (pressure) algorithm runs for all
// jobs that do not yet have an assigned flavor.
func (d *Database) AddFlavor(ctx context.Context, flavor *Flavor) error {
	batch := &pgx.Batch{}
	batch.Queue(`
		INSERT INTO flavor (
			platform, name, labels, priority, is_disabled, minimum_pressure
		) VALUES (@platform, @name, @labels, @priority, @is_disabled, @minimum_pressure)
		ON CONFLICT (name) DO NOTHING;
	`, pgx.NamedArgs{
		"platform":         flavor.Platform,
		"name":             flavor.Name,
		"labels":           flavor.Labels,
		"priority":         flavor.Priority,
		"is_disabled":      flavor.IsDisabled,
		"minimum_pressure": flavor.MinimumPressure,
	})
	batch.Queue(updateAssignedFlavorSql)
	batch.Queue(pressureChangeSql)
	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for inserting flavors", "error", err)
		}
	}()

	for i := range batch.Len() {
		tag, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to insert flavor: %w", err)
		}
		if i == 0 && tag.RowsAffected() == 0 {
			return ErrExist
		}
	}

	return nil
}

func (d *Database) setFlavorIsDisabled(ctx context.Context, platform, name string, isDisabled bool) error {
	batch := &pgx.Batch{}
	if isDisabled {
		batch.Queue(`
		UPDATE job SET assigned_flavor = NULL 
		WHERE platform = @platform AND assigned_flavor = @name
		`, pgx.NamedArgs{
			"platform": platform,
			"name":     name,
		})
	}
	batch.Queue(`
		UPDATE flavor SET is_disabled = @is_disabled
		WHERE platform = @platform AND name = @name
	`, pgx.NamedArgs{
		"platform":    platform,
		"name":        name,
		"is_disabled": isDisabled,
	})
	batch.Queue(updateAssignedFlavorSql)
	batch.Queue(pressureChangeSql)
	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for disabling flavors", "error", err)
		}
	}()

	notFound := false

	flavorUpdateIdx := 0
	if isDisabled {
		flavorUpdateIdx = 1
	}

	for i := range batch.Len() {
		tag, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to disable flavor: %w", err)
		}
		if i == flavorUpdateIdx && tag.RowsAffected() == 0 {
			notFound = true
		}
	}
	if notFound {
		return ErrNotExist
	}
	return nil
}

// DisableFlavor disables a flavor, excluding it from the flavor-assignment
// pressure algorithm. Jobs currently assigned to this flavor are reset and
// re-assigned to a new flavor using the same algorithm.
// If the flavor doesn't exist, it will return ErrNotExist.
func (d *Database) DisableFlavor(ctx context.Context, platform, name string) error {
	return d.setFlavorIsDisabled(ctx, platform, name, true)
}

// EnableFlavor enables a flavor, and reverses the DisableFlavor.
// If the flavor doesn't exist, it will return ErrNotExist.
func (d *Database) EnableFlavor(ctx context.Context, platform, name string) error {
	return d.setFlavorIsDisabled(ctx, platform, name, false)
}

// DeleteFlavor deletes a flavor.
// Jobs currently assigned to this flavor are reset and re-assigned to a new
// flavor using the same algorithm.
// If the flavor doesn't exist, it will do nothing.
func (d *Database) DeleteFlavor(ctx context.Context, platform, name string) error {
	batch := &pgx.Batch{}
	batch.Queue(`
		UPDATE job SET assigned_flavor = NULL 
		WHERE platform = @platform AND assigned_flavor = @name
	`, pgx.NamedArgs{
		"platform": platform,
		"name":     name,
	})
	batch.Queue(`
		DELETE FROM flavor
		WHERE platform = @platform AND name = @name
	`, pgx.NamedArgs{
		"platform": platform,
		"name":     name,
	})
	batch.Queue(updateAssignedFlavorSql)
	batch.Queue(pressureChangeSql)
	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for deleting flavors", "error", err)
		}
	}()

	for range batch.Len() {
		_, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to delete flavor: %w", err)
		}
	}

	return nil
}

// ListFlavors lists existing flavors.
func (d *Database) ListFlavors(ctx context.Context, platform string) ([]Flavor, error) {
	sql := `
	SELECT 
      platform, name, labels, priority, is_disabled, minimum_pressure
    FROM flavor
    WHERE platform = @platform`
	rows, err := d.conn.Query(ctx, sql, pgx.NamedArgs{"platform": platform})
	if err != nil {
		return nil, fmt.Errorf("failed to list flavors: %w", err)
	}
	flavors, err := pgx.CollectRows[Flavor](rows, pgx.RowToStructByName)
	if err != nil {
		return nil, fmt.Errorf("failed to list flavors: %w", err)
	}
	return flavors, nil
}

// GetPressures returns the pressure for the specified flavors.
// If no flavors are specified, it returns the pressure for all flavors.
// For details on how pressure is computed, see the package documentation
// on the pressure algorithm.
func (d *Database) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	sql := `
	SELECT f.name                                    AS flavor,
           GREATEST(f.minimum_pressure, COUNT(j.pk)) AS pressure
	FROM flavor AS f
			 LEFT JOIN job AS j
					   ON f.platform = j.platform
					       AND j.assigned_flavor = f.name
						   AND j.completed_at IS NULL
	WHERE f.platform = @platform
	`

	args := pgx.NamedArgs{
		"platform": platform,
	}

	// Add flavor filtering when needed
	if len(flavors) > 0 {
		sql += " AND f.name = ANY(@flavors)"
		args["flavors"] = flavors
	}

	sql += "GROUP BY f.name, f.priority, f.minimum_pressure"

	rows, err := d.conn.Query(ctx, sql, args)
	if err != nil {
		return nil, fmt.Errorf("failed to calculate flavor pressure: %w", err)
	}

	type pressureRow struct {
		Flavor   string
		Pressure int
	}

	pressureRows, err := pgx.CollectRows[pressureRow](rows, pgx.RowToStructByName)
	if err != nil {
		return nil, fmt.Errorf("failed to calculate flavor pressure: %w", err)
	}

	pressures := make(map[string]int)
	for _, row := range pressureRows {
		pressures[row.Flavor] = row.Pressure
	}
	return pressures, nil
}

func (d *Database) SubscribeToPressureUpdate(ctx context.Context) (<-chan struct{}, error) {
	pConn, err := d.conn.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to the database for pressure change event listener: %w", err)
	}
	conn := pConn.Hijack()

	_, err = conn.Exec(ctx, "LISTEN "+pressureChangeChannelName+";")
	if err != nil {
		return nil, fmt.Errorf("failed to listen for pressure change events: %w", err)
	}

	ch := make(chan struct{}, channelBufferSize)
	go func() {
		defer conn.Close(context.Background())
		defer close(ch)

		for {
			_, err := conn.WaitForNotification(ctx)
			if err != nil {
				slog.DebugContext(ctx, "Failed to receive pressure change event from database", "error", err)
				return
			}
			slog.DebugContext(ctx, "Received a pressure change event from database")
			ch <- struct{}{}
		}
	}()
	return ch, nil
}

// New creates a new Database instance
func New(ctx context.Context, uri string) (*Database, error) {
	conn, err := pgxpool.New(ctx, uri)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to the database: %v", err)
	}
	return &Database{conn: conn}, nil
}

// Close closes all database connections in the pool.
func (d *Database) Close() {
	if d.conn != nil {
		d.conn.Close()
	}
}
