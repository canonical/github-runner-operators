/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package database

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"strings"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/pgx/v5"
	"github.com/golang-migrate/migrate/v4/source/iofs"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

func Migrate(ctx context.Context, dbUri string) error {
	if !strings.HasPrefix(dbUri, "postgres://") {
		return errors.New("only postgres uri is supported")
	}

	dbUri = "pgx5://" + strings.TrimPrefix(dbUri, "postgres://")

	src, err := iofs.New(migrationsFS, "migrations")
	if err != nil {
		return fmt.Errorf("database migration source loading failed: %w", err)
	}

	m, err := migrate.NewWithSourceInstance("iofs", src, dbUri)
	if err != nil {
		return fmt.Errorf("database migration init failed: %w", err)
	}
	defer func() { _, _ = m.Close() }()

	if err := m.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return err
	}
	if sourceErr, dbErr := m.Close(); sourceErr != nil || dbErr != nil {
		return fmt.Errorf("database migration close failed: %w, %w", sourceErr, dbErr)
	}
	return nil
}
