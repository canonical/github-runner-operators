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
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"regexp"
	"sync"
	"syscall"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/planner"
	"github.com/canonical/github-runner-operators/internal/queue"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/canonical/github-runner-operators/internal/version"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const (
	dbURI             = "POSTGRESQL_DB_CONNECT_STRING"
	portEnvVar        = "APP_PORT"
	adminTokenEnvVar  = "APP_ADMIN_TOKEN_VALUE"
	serviceName       = "github-runner-planner"
	rabbitMQUriEnvVar = "RABBITMQ_CONNECT_STRING"
	platform          = "github"
	shutdownTimeout   = 30 * time.Second
	heartbeatInterval = 30 * time.Second
)

var (
	// adminTokenPattern validates admin token format: planner_v0_<exactly-20 chars from [A-Za-z0-9_-]>
	adminTokenPattern = regexp.MustCompile(`^planner_v0_[A-Za-z0-9_-]{20}$`)
)

type config struct {
	dbURI       string
	port        string
	rabbitMQURI string
	adminToken  string
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "update-flavor" {
		handleUpdateFlavor()
		return
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	err := telemetry.Start(ctx, serviceName, version.String())
	if err != nil {
		log.Fatalf("failed to start telemetry: %v", err)
	}

	cfg := loadConfig()

	if err := database.Migrate(ctx, cfg.dbURI); err != nil {
		log.Fatalln("migrate failed:", err)
	}
	db, err := database.New(ctx, cfg.dbURI)
	if err != nil {
		log.Fatalln("failed to connect to db:", err)
	}

	metrics := planner.NewMetrics(db)

	amqpConsumer := queue.NewAmqpConsumer(cfg.rabbitMQURI, queue.DefaultQueueConfig())
	consumer := planner.NewJobConsumer(amqpConsumer, db, metrics)

	var consumerWg sync.WaitGroup
	consumerWg.Add(1)
	go func() {
		defer consumerWg.Done()
		if err := consumer.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
			log.Fatalf("AMQP consumer error: %v", err)
		}
	}()

	handler := planner.NewServer(db, db, metrics, cfg.adminToken, time.Tick(heartbeatInterval))
	server := &http.Server{
		Addr:    ":" + cfg.port,
		Handler: otelhttp.NewHandler(handler, "planner-api", otelhttp.WithServerName("planner")),
	}

	go func() {
		log.Println("Starting planner API server on port", cfg.port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("Shutdown signal received, starting graceful shutdown...")

	shutdown(server, consumer, &consumerWg, db)
	log.Println("Graceful shutdown complete")
}

func loadConfig() config {
	cfg := config{}
	var found bool

	cfg.dbURI, found = os.LookupEnv(dbURI)
	if !found {
		log.Fatalln(dbURI, "environment variable not set.")
	}

	cfg.port, found = os.LookupEnv(portEnvVar)
	if !found {
		log.Fatalln(portEnvVar, "environment variable not set.")
	}

	cfg.rabbitMQURI, found = os.LookupEnv(rabbitMQUriEnvVar)
	if !found {
		log.Fatalln(rabbitMQUriEnvVar, "environment variable not set.")
	}

	cfg.adminToken, found = os.LookupEnv(adminTokenEnvVar)
	if !found {
		log.Fatalln(adminTokenEnvVar, "environment variable not set.")
	}
	if !adminTokenPattern.MatchString(cfg.adminToken) {
		log.Fatalf("%s has invalid format; expected 'planner_v0_' + exactly 20 characters from [A-Za-z0-9_-]\n", adminTokenEnvVar)
	}

	return cfg
}

func shutdown(server *http.Server, consumer *planner.JobConsumer, consumerWg *sync.WaitGroup, db *database.Database) {
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer shutdownCancel()

	log.Println("Shutting down HTTP server...")
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP server shutdown error: %v", err)
	}

	log.Println("Waiting for AMQP consumer to stop...")
	consumerWg.Wait()

	log.Println("Closing AMQP connection...")
	if err := consumer.Close(); err != nil {
		log.Printf("failed to close AMQP consumer: %v", err)
	}

	log.Println("Closing database connection...")
	db.Close()

	log.Println("Shutting down telemetry...")
	if err := telemetry.Shutdown(shutdownCtx); err != nil {
		log.Printf("failed to shutdown telemetry: %v", err)
	}
}

func handleUpdateFlavor() {
	flavorName, shouldEnable := parseUpdateFlavorFlags()
	executeFlavorUpdate(flavorName, shouldEnable)
}

func parseUpdateFlavorFlags() (string, bool) {
	updateCmd := flag.NewFlagSet("update-flavor", flag.ExitOnError)
	flavor := updateCmd.String("flavor", "", "Name of the flavor to update")
	disable := updateCmd.Bool("disable", false, "Disable the flavor")
	enable := updateCmd.Bool("enable", false, "Enable the flavor")

	if err := updateCmd.Parse(os.Args[2:]); err != nil {
		log.Fatalf("Failed to parse flags: %v", err)
	}

	if *flavor == "" {
		log.Fatalln("--flavor is required")
	}

	if *enable == *disable {
		log.Fatalln("exactly one of --enable or --disable must be specified")
	}

	return *flavor, *enable
}

func executeFlavorUpdate(flavorName string, enable bool) {
	dbURI, found := os.LookupEnv(dbURI)
	if !found {
		log.Fatalln(dbURI, "environment variable not set.")
	}

	ctx := context.Background()
	db, err := database.New(ctx, dbURI)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	if enable {
		enableFlavor(ctx, db, flavorName)
	} else {
		disableFlavor(ctx, db, flavorName)
	}
}

func enableFlavor(ctx context.Context, db *database.Database, flavorName string) {
	if err := db.EnableFlavor(ctx, platform, flavorName); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			log.Fatalf("Flavor '%s' not found", flavorName)
		}
		log.Fatalf("Failed to enable flavor: %v", err)
	}
	fmt.Printf("Flavor '%s' enabled successfully\n", flavorName)
}

func disableFlavor(ctx context.Context, db *database.Database, flavorName string) {
	if err := db.DisableFlavor(ctx, platform, flavorName); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			log.Fatalf("Flavor '%s' not found", flavorName)
		}
		log.Fatalf("Failed to disable flavor: %v", err)
	}
	fmt.Printf("Flavor '%s' disabled successfully\n", flavorName)
}
