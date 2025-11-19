/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package main starts the Planner API service.
 *
 * This service connects to the database, exposes a REST API for managing GitHub runner
 * flavors, and provides observability features via Prometheus metrics and OpenTelemetry tracing.
 */

package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/planner"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/canonical/github-runner-operators/internal/version"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const (
	dbURI       = "POSTGRESQL_DB_CONNECT_STRING"
	portEnvVar  = "APP_PORT"
	serviceName = "github-runner-planner"
)

func main() {
	ctx := context.Background()

	// Initialize telemetry
	err := telemetry.Start(ctx, serviceName, version.String())
	if err != nil {
		log.Fatalf("failed to start telemetry: %v", err)
	}
	defer func() {
		err := telemetry.Shutdown(ctx)
		if err != nil {
			slog.ErrorContext(ctx, "failed to shutdown telemetry", "error", err)
		}
	}()

	// Load environment variables
	uri, found := os.LookupEnv(dbURI)
	if !found {
		log.Fatalln(dbURI, "environment variable not set.")
	}

	port, found := os.LookupEnv(portEnvVar)
	if !found {
		log.Fatalln(portEnvVar, "environment variable not set.")
	}

	_, err = StartServer(ctx, uri, port)
	if err != nil {
		log.Fatalf("failed to start server: %v", err)
	}

	select {} // block forever
}

// StartServer initializes and starts the Planner API server.
func StartServer(ctx context.Context, uri, port string) (*http.Server, error) {
	if err := database.Migrate(ctx, uri); err != nil {
		return nil, fmt.Errorf("migrate failed: %w", err)
	}
	db, err := database.New(ctx, uri)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to db: %w", err)
	}

	metrics := planner.NewMetrics(db)
	server := planner.NewServer(db, metrics)

	srv := &http.Server{
		Addr:    ":" + port,
		Handler: otelhttp.NewHandler(server, "planner-api", otelhttp.WithServerName("planner")),
	}

	go func() {
		log.Println("Starting planner API server on port", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %s\n", err)
		}
	}()

	return srv, nil
}
