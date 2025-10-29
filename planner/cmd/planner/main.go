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

	"github.com/canonical/github-runner-operators/internal/auth"
	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/planner"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const dbURI = "PLANNER_DATABASE_URI"
const adminToken = "PLANNER_ADMIN_TOKEN"
const portEnvVar = "PLANNER_PORT"
const flavorPressureMetricName = "mayfly_planner_flavor_pressure"
const metricsPath = "/metrics"
const metricsPort = "9388"
const flavorPlatform = "github" // Currently only github is supported

func main() {
	ctx := context.Background()

	// Load environment variables
	uri, found := os.LookupEnv(dbURI)
	if !found {
		log.Fatalln(dbURI, "environment variable not set.")
	}

	token, found := os.LookupEnv(adminToken)
	if !found {
		log.Fatalln(adminToken, "environment variable not set.")
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

	server := planner.NewServer(db)
	go initializeObservability(ctx, db, server)

	// Start API server with auth middleware
	handler := auth.AuthMiddleware(server, token)
	mux := http.NewServeMux()
	mux.Handle("/", handler)

	log.Println("Starting planner API server on port", port)
	log.Fatal(http.ListenAndServe(":"+port, otelhttp.NewHandler(mux, "planner-api", otelhttp.WithServerName("planner"))))
}

// initializeObservability sets up Prometheus metrics for flavor pressure
// and starts an HTTP server to expose the metrics.
func initializeObservability(ctx context.Context, db *database.Database, server *planner.Server) {
	flavorPressure := prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: flavorPressureMetricName,
			Help: "The current pressure value for each flavor",
		},
		[]string{"platform", "flavor"},
	)
	prometheus.MustRegister(flavorPressure)

	if err := populateExistingFlavors(ctx, db, flavorPressure); err != nil {
		log.Println("Failed to populate existing flavors metrics:", err)
	}

	server.OnFlavorCreated = func(ctx context.Context, flavor *database.Flavor) {
		pressure, err := db.GetPressures(ctx, flavor.Platform, flavor.Name)
		if err != nil {
			log.Printf("Failed to fetch pressure for flavor %s: %v", flavor.Name, err)
			return
		}
		pressureValue, ok := pressure[flavor.Name]
		if !ok {
			pressureValue = 0
		}
		flavorPressure.WithLabelValues(flavor.Platform, flavor.Name).Set(float64(pressureValue))
	}

	muxMetrics := http.NewServeMux()
	muxMetrics.Handle(metricsPath, promhttp.Handler())
	log.Println("Starting metrics server on port", metricsPort)

	if err := http.ListenAndServe(":"+metricsPort, muxMetrics); err != nil {
		log.Fatalln("Failed to start metrics server:", err)
	}
}

// populateExistingFlavors initializes the flavor pressure gauge with existing flavors from the database.
func populateExistingFlavors(ctx context.Context, db *database.Database, gauge *prometheus.GaugeVec) error {
	platforms := []string{flavorPlatform}
	for _, platform := range platforms {
		// Get all flavors for the platform
		flavors, err := db.ListFlavors(ctx, platform)
		if err != nil {
			return err
		}
		if len(flavors) == 0 {
			continue
		}

		// Extract flavor names
		flavorNames := make([]string, 0, len(flavors))
		for _, flavor := range flavors {
			flavorNames = append(flavorNames, flavor.Name)
		}

		// Get pressures for the flavors
		pressures, err := db.GetPressures(ctx, platform, flavorNames...)
		if err != nil {
			return err
		}

		// Set gauge labels in the format (platform, flavor) with pressure value
		for _, flavor := range flavors {
			pressureValue, ok := pressures[flavor.Name]
			if !ok {
				pressureValue = 0
			}
			gauge.WithLabelValues(platform, flavor.Name).Set(float64(pressureValue))
		}
	}
	return nil
}
