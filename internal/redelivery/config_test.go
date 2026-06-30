/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package redelivery

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestConfigFromEnvReturnsNilWhenMissingRequiredFields(t *testing.T) {
	/*
		arrange: Leave required org/webhook environment variables unset.
		act: Build config from environment.
		assert: Nil config is returned because redelivery is not configured.
	*/
	t.Setenv(GitHubPathEnvVar, "")
	t.Setenv(WebhookIDEnvVar, "")

	cfg, err := ConfigFromEnv()

	require.NoError(t, err)
	assert.Nil(t, cfg)
}

func TestConfigFromEnvParsesAppAuthFields(t *testing.T) {
	/*
		arrange: Set app auth environment variables.
		act: Build config from environment.
		assert: App auth fields are parsed into config.
	*/
	t.Setenv(GitHubPathEnvVar, "test-org")
	t.Setenv(WebhookIDEnvVar, "7")
	t.Setenv(GitHubAppIDEnvVar, "99")
	t.Setenv(GitHubAppInstallationIDEnvVar, "100")
	t.Setenv(GitHubAppPrivateKeyEnvVar, "private-key")

	cfg, err := ConfigFromEnv()

	require.NoError(t, err)
	require.NotNil(t, cfg)
	assert.Equal(t, "test-org", cfg.GitHubOrg)
	assert.Equal(t, "", cfg.GitHubRepo)
	assert.Equal(t, int64(99), cfg.GitHubAppID)
	assert.Equal(t, int64(100), cfg.GitHubAppInstallationID)
	assert.Equal(t, "private-key", cfg.GitHubAppPrivateKey)
}

func TestConfigFromEnvReturnsErrorOnInvalidWebhookID(t *testing.T) {
	/*
		arrange: Set required env vars with non-numeric webhook ID.
		act: Build config from environment.
		assert: Parsing error is returned.
	*/
	t.Setenv(GitHubPathEnvVar, "test-org")
	t.Setenv(WebhookIDEnvVar, "not-a-number")

	cfg, err := ConfigFromEnv()

	assert.Nil(t, cfg)
	assert.ErrorContains(t, err, "invalid "+WebhookIDEnvVar+" value")
}

func TestIntervalDefaultsToConfiguredValue(t *testing.T) {
	/*
		arrange: Create configs with and without explicit intervals.
		act: Resolve each config interval.
		assert: Zero interval maps to default and explicit value is preserved.
	*/
	zeroIntervalCfg := &Config{}
	explicitIntervalCfg := &Config{Interval: 3 * time.Minute}

	assert.Equal(t, defaultInterval, zeroIntervalCfg.interval())
	assert.Equal(t, 3*time.Minute, explicitIntervalCfg.interval())
}

func TestNewDaemonRejectsInvalidConfig(t *testing.T) {
	/*
		arrange: Create a config that fails validation.
		act: Construct daemon from config.
		assert: An invalid config error is returned.
	*/
	cfg := &Config{GitHubOrg: "org", WebhookID: 1}

	daemon, err := NewDaemon(cfg)

	assert.Nil(t, daemon)
	assert.ErrorContains(t, err, "invalid redelivery config")
}

func TestConfigFromEnvParsesGitHubPathWithRepo(t *testing.T) {
	/*
		arrange: Set github path with org/repo format.
		act: Build config from environment.
		assert: Org and repo are parsed correctly.
	*/
	t.Setenv(GitHubPathEnvVar, "my-org/my-repo")
	t.Setenv(WebhookIDEnvVar, "42")

	cfg, err := ConfigFromEnv()

	require.NoError(t, err)
	require.NotNil(t, cfg)
	assert.Equal(t, "my-org", cfg.GitHubOrg)
	assert.Equal(t, "my-repo", cfg.GitHubRepo)
}

func TestParseGitHubPath(t *testing.T) {
	tests := []struct {
		name     string
		path     string
		wantOrg  string
		wantRepo string
	}{
		{name: "org only", path: "my-org", wantOrg: "my-org", wantRepo: ""},
		{name: "org and repo", path: "my-org/my-repo", wantOrg: "my-org", wantRepo: "my-repo"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			org, repo := parseGitHubPath(tc.path)
			assert.Equal(t, tc.wantOrg, org)
			assert.Equal(t, tc.wantRepo, repo)
		})
	}
}
