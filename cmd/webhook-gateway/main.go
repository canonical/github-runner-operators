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
	"strconv"
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

const githubTokenEnvVar = "APP_GITHUB_TOKEN_VALUE"
const githubAppClientIDEnvVar = "APP_GITHUB_APP_CLIENT_ID"
const githubAppInstallationIDEnvVar = "APP_GITHUB_APP_INSTALLATION_ID"
const githubAppPrivateKeyEnvVar = "APP_GITHUB_APP_PRIVATE_KEY_VALUE"
const webhookGitHubOrgEnvVar = "APP_WEBHOOK_GITHUB_ORG"
const webhookGitHubRepoEnvVar = "APP_WEBHOOK_GITHUB_REPO"
const webhookIDEnvVar = "APP_WEBHOOK_ID"
const redeliveryIntervalEnvVar = "APP_REDELIVERY_INTERVAL_SECONDS"

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
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
	cfg := buildRedeliveryConfig()
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

func buildRedeliveryConfig() *redelivery.Config {
	githubOrg := os.Getenv(webhookGitHubOrgEnvVar)
	webhookIDStr := os.Getenv(webhookIDEnvVar)
	if githubOrg == "" || webhookIDStr == "" {
		return nil
	}

	webhookID, err := strconv.ParseInt(webhookIDStr, 10, 64)
	if err != nil {
		log.Fatalf("invalid %s value: %v", webhookIDEnvVar, err)
	}

	cfg := &redelivery.Config{
		GitHubToken: os.Getenv(githubTokenEnvVar),
		GitHubOrg:   githubOrg,
		GitHubRepo:  os.Getenv(webhookGitHubRepoEnvVar),
		WebhookID:   webhookID,
	}

	if appIDStr := os.Getenv(githubAppClientIDEnvVar); appIDStr != "" {
		appID, err := strconv.ParseInt(appIDStr, 10, 64)
		if err != nil {
			log.Fatalf("invalid %s value: %v", githubAppClientIDEnvVar, err)
		}
		cfg.GitHubAppID = appID

		installationIDStr := os.Getenv(githubAppInstallationIDEnvVar)
		installationID, err := strconv.ParseInt(installationIDStr, 10, 64)
		if err != nil {
			log.Fatalf("invalid %s value: %v", githubAppInstallationIDEnvVar, err)
		}
		cfg.GitHubAppInstallationID = installationID
		cfg.GitHubAppPrivateKey = os.Getenv(githubAppPrivateKeyEnvVar)
	}

	if intervalStr := os.Getenv(redeliveryIntervalEnvVar); intervalStr != "" {
		seconds, err := strconv.Atoi(intervalStr)
		if err != nil {
			log.Fatalf("invalid %s value: %v", redeliveryIntervalEnvVar, err)
		}
		cfg.Interval = time.Duration(seconds) * time.Second
	}

	return cfg
}
