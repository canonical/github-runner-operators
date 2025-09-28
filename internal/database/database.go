package database

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const (
	DefaultLimit            = 100
	updateAssignedFlavorSql = `
	UPDATE job AS j
	SET assigned_flavor = (SELECT f.name
						   FROM flavor AS f
						   WHERE f.is_disabled = FALSE
							 AND f.platform = j.platform
							 AND f.labels @> j.labels
						   ORDER BY f.priority DESC, random()
						   LIMIT 1)
	WHERE j.assigned_flavor IS NULL
	  AND EXISTS (SELECT 1
				  FROM flavor AS f
				  WHERE f.is_disabled = FALSE
					AND f.platform = j.platform
					AND f.labels @> j.labels
					AND j.completed_at IS NULL);
`
)

var ErrNotFound = errors.New("not found")

type Database struct {
	conn *pgxpool.Pool
}

type ListJobOptions struct {
	WithId           string
	OnlyNotCompleted bool
	CreatedAfter     time.Time
	Limit            int
}

func (d *Database) CreateAuthToken(ctx context.Context, name, token string) error {
	_, err := d.conn.Exec(ctx, "INSERT INTO auth (name, token) VALUES ($1, $2)", name, token)
	if err != nil {
		return fmt.Errorf("failed to insert auth token: %w", err)
	}
	return nil
}

func (d *Database) GetAuthToken(ctx context.Context, name string) (string, error) {
	row := d.conn.QueryRow(ctx, "SELECT token FROM auth WHERE name = $1", name)
	var token string
	if err := row.Scan(&token); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", ErrNotFound
		}
		return "", fmt.Errorf("failed to get auth token: %w", err)
	}
	return token, nil
}

func (d *Database) DeleteAuthToken(ctx context.Context, name string) error {
	_, err := d.conn.Exec(ctx, "DELETE FROM auth WHERE name = $1", name)
	if err != nil {
		return fmt.Errorf("failed to delete auth token: %w", err)
	}
	return nil
}

func (d *Database) AddJob(ctx context.Context, job *Job) error {
	const sql = `
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
	  END;
	`

	raw := job.Raw
	if raw == nil {
		raw = map[string]interface{}{}
	}

	_, err := d.conn.Exec(ctx, sql, pgx.NamedArgs{
		"platform":     job.Platform,
		"id":           job.ID,
		"labels":       job.Labels,
		"created_at":   job.CreatedAt,
		"started_at":   job.StartedAt,
		"completed_at": job.CompletedAt,
		"raw":          raw,
	})
	if err != nil {
		return fmt.Errorf("failed to insert job: %w", err)
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

	sql += fmt.Sprintf("\n ORDER BY created_at LIMIT @limit")
	args["limit"] = limit
	return sql, args
}

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
		return ErrNotFound
	}
	return nil
}

func (d *Database) UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]interface{}) error {
	const stmt = `
		UPDATE job
		SET
			completed_at = @completed_at,
			raw = COALESCE(job.raw, '{}'::jsonb) || COALESCE(@raw::jsonb, '{}'::jsonb)
		WHERE platform = @platform AND id = @id;
	`

	tag, err := d.conn.Exec(ctx, stmt, pgx.NamedArgs{
		"platform":     platform,
		"id":           id,
		"completed_at": completedAt,
		"raw":          raw,
	})
	if err != nil {
		return fmt.Errorf("failed to update job completed_at time: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (d *Database) AddFlavor(ctx context.Context, flavor *Flavor) error {
	batch := &pgx.Batch{}
	batch.Queue(`
		INSERT INTO flavor (
			platform, name, labels, priority, is_disabled, minimum_pressure
		) VALUES (@platform, @name, @labels, @priority, @is_disabled, @minimum_pressure)
	`, pgx.NamedArgs{
		"platform":         flavor.Platform,
		"name":             flavor.Name,
		"labels":           flavor.Labels,
		"priority":         flavor.Priority,
		"is_disabled":      flavor.IsDisabled,
		"minimum_pressure": flavor.MinimumPressure,
	})
	batch.Queue(updateAssignedFlavorSql)

	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for inserting flavors", "error", err)
		}
	}()

	for range batch.Len() {
		_, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to insert flavor: %w", err)
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
	result := d.conn.SendBatch(ctx, batch)
	defer func() {
		err := result.Close()
		if err != nil {
			slog.ErrorContext(ctx, "failed to close batch execution for disabling flavors", "error", err)
		}
	}()

	notFound := false

	for i := range batch.Len() {
		tag, err := result.Exec()
		if err != nil {
			return fmt.Errorf("failed to disable flavor: %w", err)
		}
		if i == 0 && tag.RowsAffected() == 0 {
			notFound = true
		}
	}
	if notFound {
		return ErrNotFound
	}
	return nil
}

func (d *Database) DisableFlavor(ctx context.Context, platform, name string) error {
	return d.setFlavorIsDisabled(ctx, platform, name, true)
}

func (d *Database) EnableFlavor(ctx context.Context, platform, name string) error {
	return d.setFlavorIsDisabled(ctx, platform, name, false)
}

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

func (d *Database) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	sql := `
	SELECT f.name                                    AS flavor,
           GREATEST(f.minimum_pressure, COUNT(j.pk)) AS pressure
	FROM flavor AS f
			 LEFT JOIN job AS j
					   ON f.platform = j.platform
					       AND j.assigned_flavor = f.name
						   AND j.completed_at IS NULL
	WHERE f.platform = @platform AND f.name = ANY(@flavors)
	GROUP BY f.name, f.priority, f.minimum_pressure
	`
	rows, err := d.conn.Query(ctx, sql, pgx.NamedArgs{
		"platform": platform,
		"flavors":  flavors,
	})
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
	for _, flavor := range flavors {
		pressures[flavor] = 0
	}
	for _, row := range pressureRows {
		pressures[row.Flavor] = row.Pressure
	}
	return pressures, nil
}

func New(ctx context.Context, uri string) (*Database, error) {
	conn, err := pgxpool.New(ctx, uri)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to the database: %v", err)
	}
	return &Database{conn: conn}, nil
}
