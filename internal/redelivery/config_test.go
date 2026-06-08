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
	t.Setenv(WebhookGitHubOrgEnvVar, "")
	t.Setenv(WebhookIDEnvVar, "")

	cfg := ConfigFromEnv()

	assert.Nil(t, cfg)
}

func TestConfigFromEnvParsesTokenAuthAndInterval(t *testing.T) {
	/*
		arrange: Set token auth and interval environment variables.
		act: Build config from environment.
		assert: Token auth fields and interval are parsed into config.
	*/
	t.Setenv(WebhookGitHubOrgEnvVar, "test-org")
	t.Setenv(WebhookGitHubRepoEnvVar, "test-repo")
	t.Setenv(WebhookIDEnvVar, "42")
	t.Setenv(GitHubTokenEnvVar, "token")
	t.Setenv(RedeliveryIntervalEnvVar, "15")

	cfg := ConfigFromEnv()

	require.NotNil(t, cfg)
	assert.Equal(t, "test-org", cfg.GitHubOrg)
	assert.Equal(t, "test-repo", cfg.GitHubRepo)
	assert.Equal(t, int64(42), cfg.WebhookID)
	assert.Equal(t, "token", cfg.GitHubToken)
	assert.Equal(t, 15*time.Second, cfg.Interval)
}

func TestConfigFromEnvParsesAppAuthFields(t *testing.T) {
	/*
		arrange: Set app auth environment variables.
		act: Build config from environment.
		assert: App auth fields are parsed into config.
	*/
	t.Setenv(WebhookGitHubOrgEnvVar, "test-org")
	t.Setenv(WebhookIDEnvVar, "7")
	t.Setenv(GitHubAppIDEnvVar, "99")
	t.Setenv(GitHubAppInstallationIDEnvVar, "100")
	t.Setenv(GitHubAppPrivateKeyEnvVar, "private-key")

	cfg := ConfigFromEnv()

	require.NotNil(t, cfg)
	assert.Equal(t, int64(99), cfg.GitHubAppID)
	assert.Equal(t, int64(100), cfg.GitHubAppInstallationID)
	assert.Equal(t, "private-key", cfg.GitHubAppPrivateKey)
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

func TestNewDaemonReturnsClientCreationErrorForInvalidAppKey(t *testing.T) {
	/*
		arrange: Create app-auth config with an invalid private key.
		act: Construct daemon from config.
		assert: Client creation fails with a wrapped error.
	*/
	cfg := &Config{
		GitHubOrg:               "org",
		WebhookID:               1,
		GitHubAppID:             1,
		GitHubAppInstallationID: 2,
		GitHubAppPrivateKey:     "invalid-private-key",
	}

	daemon, err := NewDaemon(cfg)

	assert.Nil(t, daemon)
	assert.ErrorContains(t, err, "cannot create github client")
}

func TestNewDaemonWithTokenAuthSucceeds(t *testing.T) {
	/*
		arrange: Create valid token-auth config.
		act: Construct daemon from config.
		assert: Daemon is created successfully.
	*/
	cfg := &Config{
		GitHubToken: "token",
		GitHubOrg:   "org",
		WebhookID:   1,
	}

	daemon, err := NewDaemon(cfg)

	require.NoError(t, err)
	assert.NotNil(t, daemon)
}
