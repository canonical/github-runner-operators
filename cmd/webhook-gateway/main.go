/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package main

import (
	"context"
	"log"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/canonical/github-runner-operators/internal/queue"
	"github.com/canonical/github-runner-operators/internal/redelivery"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/canonical/github-runner-operators/internal/version"
	"github.com/canonical/github-runner-operators/internal/webhook"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const webhookPath = "/webhook"
const portEnvVar = "APP_PORT"
const rabbitMQUriEnvVar = "RABBITMQ_CONNECT_STRING"
const webhookSecretEnvVar = "APP_WEBHOOK_SECRET_VALUE"

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM)
	defer stop()

	err := telemetry.Start(ctx, "github-runner-webhook-gateway", version.String())
	if err != nil {
		log.Fatalf("failed to start telemetry: %v", err)
	}
	defer func() {
		err := telemetry.Shutdown(ctx)
		if err != nil {
			slog.ErrorContext(ctx, "failed to shutdown telemetry", "error", err)
		}
	}()

	port, found := os.LookupEnv(portEnvVar)
	if !found {
		log.Fatalln(portEnvVar + " environment variable not set")
	}
	uri, found := os.LookupEnv(rabbitMQUriEnvVar)
	if !found {
		log.Fatalln(rabbitMQUriEnvVar + " environment variable not set")
	}
	webhookSecret, found := os.LookupEnv(webhookSecretEnvVar)
	if !found {
		log.Fatalln(webhookSecretEnvVar + " environment variable not set")
	}

	var wg sync.WaitGroup
	startRedeliveryDaemon(ctx, &wg)

	p := queue.NewAmqpProducer(uri, queue.DefaultQueueConfig())
	handler := &webhook.Handler{
		WebhookSecret: webhookSecret,
		Producer:      p,
	}

	mux := http.NewServeMux()
	mux.HandleFunc(webhookPath, handler.Webhook)

	srv := &http.Server{
		Addr:    ":" + port,
		Handler: otelhttp.NewHandler(mux, "", otelhttp.WithServerName("")),
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			slog.ErrorContext(ctx, "http server shutdown error", "error", err)
		}
	}()

	slog.InfoContext(ctx, "starting webhook gateway", "port", port)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("http server failed: %v", err)
	}

	wg.Wait()
}

func startRedeliveryDaemon(ctx context.Context, wg *sync.WaitGroup) {
	cfg := redelivery.ConfigFromEnv()
	if cfg == nil {
		return
	}
	daemon, err := redelivery.NewDaemon(cfg)
	if err != nil {
		log.Fatalf("failed to create redelivery daemon: %v", err)
	}
	wg.Add(1)
	go func() {
		defer wg.Done()
		daemon.Run(ctx)
	}()
}
