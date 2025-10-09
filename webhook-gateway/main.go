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

	"github.com/canonical/mayfly/internal/queue"
	"github.com/canonical/mayfly/internal/telemetry"
	"github.com/canonical/mayfly/internal/version"
	"github.com/canonical/mayfly/internal/webhook"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const queueName = "webhook-queue"
const webhookPath = "/webhook"
const portEnvVar = "APP_PORT"
const rabbitMQUriEnvVar = "RABBITMQ_CONNECT_STRING"
const webhookSecretEnvVar = "APP_WEBHOOK_SECRET_VALUE"

func main() {
	ctx := context.Background()
	err := telemetry.Start(ctx, "mayfly-webhook-router", version.String())
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

	p := queue.NewAmqpProducer(uri, queueName)
	handler := &webhook.Handler{
		WebhookSecret: webhookSecret,
		Producer:      p,
	}

	mux := http.NewServeMux()
	mux.HandleFunc(webhookPath, handler.Webhook)

	log.Fatal(http.ListenAndServe(":"+port, otelhttp.NewHandler(mux, "", otelhttp.WithServerName(""))))
}
