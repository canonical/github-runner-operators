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

	// Connect to database and create server
	db, err := database.New(ctx, uri)
	if err != nil {
		log.Fatalln("failed to connect to db:", err)
	}

	metrics := planner.NewMetrics(db)
	server := planner.NewServer(db, metrics)

	log.Println("Starting planner API server on port", port)
	log.Fatal(http.ListenAndServe(":"+port, otelhttp.NewHandler(server, "planner-api", otelhttp.WithServerName("planner"))))
}
