/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package redelivery

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

// Environment variable names for redelivery configuration.
const (
	GitHubAppIDEnvVar             = "APP_GITHUB_APP_ID"
	GitHubAppInstallationIDEnvVar = "APP_GITHUB_APP_INSTALLATION_ID"
	GitHubAppPrivateKeyEnvVar     = "APP_GITHUB_APP_PRIVATE_KEY_VALUE"
	WebhookGitHubOrgEnvVar        = "APP_WEBHOOK_GITHUB_ORG"
	WebhookGitHubRepoEnvVar       = "APP_WEBHOOK_GITHUB_REPO"
	WebhookIDEnvVar               = "APP_WEBHOOK_ID"
	RedeliveryIntervalEnvVar      = "APP_REDELIVERY_INTERVAL_SECONDS"
)

// ConfigFromEnv builds a redelivery config from environment variables.
// Returns nil if redelivery is not configured (missing org or webhook ID).
func ConfigFromEnv() (*Config, error) {
	githubOrg := os.Getenv(WebhookGitHubOrgEnvVar)
	webhookIDStr := os.Getenv(WebhookIDEnvVar)
	if githubOrg == "" || webhookIDStr == "" {
		return nil, nil
	}

	webhookID, err := strconv.ParseInt(webhookIDStr, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("invalid %s value: %w", WebhookIDEnvVar, err)
	}

	cfg := &Config{
		GitHubOrg:  githubOrg,
		GitHubRepo: os.Getenv(WebhookGitHubRepoEnvVar),
		WebhookID:  webhookID,
	}

	if err := configureAuth(cfg); err != nil {
		return nil, err
	}
	if err := configureInterval(cfg); err != nil {
		return nil, err
	}

	return cfg, nil
}

func configureAuth(cfg *Config) error {
	appIDStr := os.Getenv(GitHubAppIDEnvVar)
	if appIDStr != "" {
		appID, err := strconv.ParseInt(appIDStr, 10, 64)
		if err != nil {
			return fmt.Errorf("invalid %s value: %w", GitHubAppIDEnvVar, err)
		}
		cfg.GitHubAppID = appID
	}

	installationIDStr := os.Getenv(GitHubAppInstallationIDEnvVar)
	if installationIDStr != "" {
		installationID, err := strconv.ParseInt(installationIDStr, 10, 64)
		if err != nil {
			return fmt.Errorf("invalid %s value: %w", GitHubAppInstallationIDEnvVar, err)
		}
		cfg.GitHubAppInstallationID = installationID
	}
	cfg.GitHubAppPrivateKey = os.Getenv(GitHubAppPrivateKeyEnvVar)

	return nil
}

func configureInterval(cfg *Config) error {
	intervalStr := os.Getenv(RedeliveryIntervalEnvVar)
	if intervalStr == "" {
		return nil
	}

	seconds, err := strconv.Atoi(intervalStr)
	if err != nil {
		return fmt.Errorf("invalid %s value: %w", RedeliveryIntervalEnvVar, err)
	}
	cfg.Interval = time.Duration(seconds) * time.Second

	return nil
}
