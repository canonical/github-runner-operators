/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

// Package redelivery implements a daemon that periodically re-delivers failed GitHub webhook deliveries.
package redelivery

import (
	"context"
	"fmt"
	"log/slog"
	"slices"
	"time"

	"github.com/google/go-github/v86/github"
)

const (
	defaultInterval = 10 * time.Minute
	supportedEvent  = "workflow_job"
	okStatus        = "OK"
)

var redeliverableActions = []string{"queued", "completed"}

// Config holds the configuration for the redelivery daemon.
type Config struct {
	// GitHubToken is the personal access token for GitHub API authentication.
	// Mutually exclusive with app-based auth fields.
	GitHubToken string

	// GitHubAppID is the GitHub App ID for app-based authentication.
	GitHubAppID int64

	// GitHubAppInstallationID is the GitHub App installation ID.
	GitHubAppInstallationID int64

	// GitHubAppPrivateKey is the PEM-encoded private key for the GitHub App.
	GitHubAppPrivateKey string

	// GitHubOrg is the GitHub organization where the webhook is registered.
	GitHubOrg string

	// GitHubRepo is the GitHub repository (optional, for repo-level webhooks).
	GitHubRepo string

	// WebhookID is the identifier of the webhook to check deliveries for.
	WebhookID int64

	// Interval is the polling interval between redelivery checks.
	// Defaults to 10 minutes if zero.
	Interval time.Duration
}

// Validate checks that the config has all required fields.
func (c *Config) Validate() error {
	if c.GitHubToken == "" && c.GitHubAppID == 0 {
		return fmt.Errorf("github authentication not configured: set either token or app credentials")
	}
	if c.GitHubToken != "" && (c.GitHubAppID != 0 || c.GitHubAppInstallationID != 0 || c.GitHubAppPrivateKey != "") {
		return fmt.Errorf("github authentication is ambiguous: set either token or app credentials, not both")
	}
	if c.GitHubAppID != 0 {
		if c.GitHubAppInstallationID == 0 {
			return fmt.Errorf("github app installation ID is required for app authentication")
		}
		if c.GitHubAppPrivateKey == "" {
			return fmt.Errorf("github app private key is required for app authentication")
		}
	}
	if c.GitHubOrg == "" {
		return fmt.Errorf("github organisation is required")
	}
	if c.WebhookID == 0 {
		return fmt.Errorf("webhook ID is required")
	}
	return nil
}

func (c *Config) interval() time.Duration {
	if c.Interval == 0 {
		return defaultInterval
	}
	return c.Interval
}

// Daemon periodically checks for failed webhook deliveries and re-delivers them.
type Daemon struct {
	config *Config
	client GitHubClient
}

// NewDaemon creates a new redelivery daemon with the given config.
func NewDaemon(cfg *Config) (*Daemon, error) {
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("invalid redelivery config: %w", err)
	}

	client, err := newGitHubClient(cfg)
	if err != nil {
		return nil, fmt.Errorf("cannot create github client: %w", err)
	}

	return &Daemon{
		config: cfg,
		client: client,
	}, nil
}

// NewDaemonWithClient creates a daemon with an injected client (for testing).
func NewDaemonWithClient(cfg *Config, client GitHubClient) *Daemon {
	return &Daemon{
		config: cfg,
		client: client,
	}
}

// Run starts the periodic redelivery loop. It blocks until the context is cancelled.
func (d *Daemon) Run(ctx context.Context) {
	interval := d.config.interval()
	logger.InfoContext(ctx, "redelivery daemon started",
		slog.Duration("interval", interval),
		slog.String("org", d.config.GitHubOrg),
		slog.String("repo", d.config.GitHubRepo),
		slog.Int64("webhook_id", d.config.WebhookID),
	)

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			logger.InfoContext(ctx, "redelivery daemon stopped")
			return
		case <-ticker.C:
			d.runOnce(ctx)
		}
	}
}

func (d *Daemon) runOnce(ctx context.Context) {
	ctx, span := tracer.Start(ctx, "redeliver failed webhooks")
	defer span.End()

	count, err := d.redeliverFailedDeliveries(ctx)
	if err != nil {
		logger.ErrorContext(ctx, "redelivery cycle failed", "error", err)
		redeliveryErrors.Add(ctx, 1)
		span.RecordError(err)
		return
	}

	if count > 0 {
		logger.InfoContext(ctx, "redelivered failed webhooks", slog.Int("count", count))
	}
	redeliveryCount.Add(ctx, int64(count))
}

func (d *Daemon) redeliverFailedDeliveries(ctx context.Context) (int, error) {
	since := time.Now().UTC().Add(-d.config.interval())

	deliveries, err := d.client.ListDeliveries(ctx, d.config.GitHubOrg, d.config.GitHubRepo, d.config.WebhookID, since)
	if err != nil {
		return 0, fmt.Errorf("cannot list webhook deliveries: %w", err)
	}

	var redelivered int
	for _, delivery := range deliveries {
		if !isFailedRoutableDelivery(delivery) {
			continue
		}

		err := d.client.RedeliverDelivery(ctx, d.config.GitHubOrg, d.config.GitHubRepo, d.config.WebhookID, delivery.GetID())
		if err != nil {
			logger.ErrorContext(ctx, "cannot redeliver webhook",
				slog.Int64("delivery_id", delivery.GetID()),
				"error", err,
			)
			continue
		}
		redelivered++
	}

	return redelivered, nil
}

func isFailedRoutableDelivery(d *github.HookDelivery) bool {
	if d.GetStatus() == okStatus {
		return false
	}
	if d.GetEvent() != supportedEvent {
		return false
	}
	return slices.Contains(redeliverableActions, d.GetAction())
}
