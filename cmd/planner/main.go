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
	shutdownTimeout   = 30 * time.Second
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	err := telemetry.Start(ctx, serviceName, version.String())
	if err != nil {
		log.Fatalf("failed to start telemetry: %v", err)
	}

	uri, found := os.LookupEnv(dbURI)
	if !found {
		log.Fatalln(dbURI, "environment variable not set.")
	}

	port, found := os.LookupEnv(portEnvVar)
	if !found {
		log.Fatalln(portEnvVar, "environment variable not set.")
	}

	rabbitMQUri, found := os.LookupEnv(rabbitMQUriEnvVar)
	if !found {
		log.Fatalln(rabbitMQUriEnvVar, "environment variable not set.")
	}

	adminToken, found := os.LookupEnv(adminTokenEnvVar)
	if !found {
		log.Fatalln(adminTokenEnvVar, "environment variable not set.")
	}
	// Validate admin token format: planner_v0_<exactly-20 chars from [A-Za-z0-9_-]>
	re := regexp.MustCompile(`^planner_v0_[A-Za-z0-9_-]{20}$`)
	if !re.MatchString(adminToken) {
		log.Fatalln("APP_ADMIN_TOKEN_VALUE has invalid format; expected 'planner_v0_' + exactly 20 characters from [A-Za-z0-9_-]")
	}

	if err := database.Migrate(ctx, uri); err != nil {
		log.Fatalln("migrate failed:", err)
	}
	db, err := database.New(ctx, uri)
	if err != nil {
		log.Fatalln("failed to connect to db:", err)
	}

	metrics := planner.NewMetrics(db)

	amqpConsumer := queue.NewAmqpConsumer(rabbitMQUri, queue.DefaultQueueConfig())
	consumer := planner.NewJobConsumer(amqpConsumer, db, metrics)

	var consumerWg sync.WaitGroup
	consumerWg.Add(1)
	go func() {
		defer consumerWg.Done()
		if err := consumer.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
			log.Fatalf("AMQP consumer error: %v", err)
		}
	}()

	handler := planner.NewServer(db, db, metrics, adminToken)
	server := &http.Server{
		Addr:    ":" + port,
		Handler: otelhttp.NewHandler(handler, "planner-api", otelhttp.WithServerName("planner")),
	}

	go func() {
		log.Println("Starting planner API server on port", port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("Shutdown signal received, starting graceful shutdown...")

	shutdown(server, consumer, &consumerWg, db)
	log.Println("Graceful shutdown complete")
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
