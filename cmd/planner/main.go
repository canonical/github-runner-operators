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
	serviceName       = "github-runner-planner"
	rabbitMQUriEnvVar = "RABBITMQ_CONNECT_STRING"
	queueName         = "webhook-queue"
	shutdownTimeout   = 30 * time.Second
)

func main() {
	// Create context that listens for shutdown signals
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	// Initialize telemetry
	err := telemetry.Start(ctx, serviceName, version.String())
	if err != nil {
		log.Fatalf("failed to start telemetry: %v", err)
	}

	// Load environment variables
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

	// Connect to database and create server
	if err := database.Migrate(ctx, uri); err != nil {
		log.Fatalln("migrate failed:", err)
	}
	db, err := database.New(ctx, uri)
	if err != nil {
		log.Fatalln("failed to connect to db:", err)
	}

	// Start AMQP consumer
	consumer := queue.NewAmqpConsumer(rabbitMQUri, queueName, db, nil)
	var consumerWg sync.WaitGroup
	consumerWg.Add(1)
	go func() {
		defer consumerWg.Done()
		if err := consumer.Start(ctx); err != nil && !errors.Is(err, context.Canceled) {
			log.Printf("AMQP consumer error: %v", err)
		}
	}()

	// Create HTTP server
	metrics := planner.NewMetrics(db)
	handler := planner.NewServer(db, metrics)
	server := &http.Server{
		Addr:    ":" + port,
		Handler: otelhttp.NewHandler(handler, "planner-api", otelhttp.WithServerName("planner")),
	}

	// Start HTTP server
	go func() {
		log.Println("Starting planner API server on port", port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	// Wait for shutdown signal
	<-ctx.Done()
	log.Println("Shutdown signal received, starting graceful shutdown...")

	// Create shutdown context with timeout
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer shutdownCancel()

	// Shutdown HTTP server (stop accepting new requests)
	log.Println("Shutting down HTTP server...")
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP server shutdown error: %v", err)
	}

	// Wait for consumer to finish processing current message
	log.Println("Waiting for AMQP consumer to stop...")
	consumerWg.Wait()

	// Close AMQP connection
	log.Println("Closing AMQP connection...")
	if err := consumer.Close(); err != nil {
		log.Printf("failed to close AMQP consumer: %v", err)
	}

	// Close database connection pool
	log.Println("Closing database connection...")
	db.Close()

	// Shutdown telemetry (flush metrics and traces)
	log.Println("Shutting down telemetry...")
	if err := telemetry.Shutdown(shutdownCtx); err != nil {
		log.Printf("failed to shutdown telemetry: %v", err)
	}

	log.Println("Graceful shutdown complete")
}
