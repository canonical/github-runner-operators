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
	"net/http"
	"os"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/planner"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const dbURI = "POSTGRESQL_DB_CONNECT_STRING"
const portEnvVar = "POSTGRESQL_DB_PORT"
const metricsPath = "/metrics"
const metricsPort = "9388"

func main() {
	ctx := context.Background()

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
		log.Fatalln("Failed to connect to db:", err)
	}

	// Create a non-global Prometheus registry
	reg := prometheus.NewRegistry()
	metrics := planner.NewMetrics(reg)
	if err := metrics.PopulateExistingFlavors(ctx, db); err != nil {
		log.Println("Failed to populate existing flavors metrics:", err)
	}

	server := planner.NewServer(db, metrics)

	go func() {
		muxMetrics := http.NewServeMux()
		muxMetrics.Handle(metricsPath, promhttp.HandlerFor(reg, promhttp.HandlerOpts{Registry: reg}))
		log.Println("Starting metrics server on port", metricsPort)
		log.Fatal(http.ListenAndServe(":"+metricsPort, muxMetrics))
	}()

	log.Println("Starting planner API server on port", port)
	log.Fatal(http.ListenAndServe(":"+port, otelhttp.NewHandler(server, "planner-api", otelhttp.WithServerName("planner"))))
}
