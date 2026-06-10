/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package redelivery

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/google/go-github/v88/github"
	"github.com/stretchr/testify/assert"
)

const (
	testOrg       = "test-org"
	testRepo      = "test-repo"
	testWebhookID = int64(12345)
	testAppID     = int64(123)
	testInstallID = int64(456)
	testAppKey    = "test-private-key"
)

type fakeGitHubClient struct {
	deliveries   []*github.HookDelivery
	redelivered  []int64
	listErr      error
	redeliverErr error
}

func (f *fakeGitHubClient) ListDeliveries(_ context.Context, _, _ string, _ int64, _ time.Time) ([]*github.HookDelivery, error) {
	if f.listErr != nil {
		return nil, f.listErr
	}
	return f.deliveries, nil
}

func (f *fakeGitHubClient) RedeliverDelivery(_ context.Context, _, _ string, _, deliveryID int64) error {
	if f.redeliverErr != nil {
		return f.redeliverErr
	}
	f.redelivered = append(f.redelivered, deliveryID)
	return nil
}

func makeDelivery(id int64, status, event, action string, deliveredAt time.Time) *github.HookDelivery {
	return &github.HookDelivery{
		ID:          github.Ptr(id),
		Status:      github.Ptr(status),
		Event:       github.Ptr(event),
		Action:      github.Ptr(action),
		DeliveredAt: &github.Timestamp{Time: deliveredAt},
	}
}

func TestRedeliverFailedDeliveries(t *testing.T) {
	/*
		arrange: Create a daemon with mixed delivery statuses and telemetry metric reader.
		act: Run a single redelivery cycle.
		assert: Only failed workflow_job queued/completed deliveries are redelivered,
		        and metrics are updated.
	*/
	mr := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	now := time.Now().UTC()
	recentFailed := makeDelivery(1, "failed", "workflow_job", "queued", now.Add(-2*time.Minute))
	recentOK := makeDelivery(2, "OK", "workflow_job", "queued", now.Add(-3*time.Minute))
	recentWrongEvent := makeDelivery(3, "failed", "push", "queued", now.Add(-4*time.Minute))
	recentCompleted := makeDelivery(4, "failed", "workflow_job", "completed", now.Add(-5*time.Minute))
	recentInProgress := makeDelivery(5, "failed", "workflow_job", "in_progress", now.Add(-6*time.Minute))
	recentWaiting := makeDelivery(6, "failed", "workflow_job", "waiting", now.Add(-7*time.Minute))

	client := &fakeGitHubClient{
		deliveries: []*github.HookDelivery{
			recentFailed,
			recentOK,
			recentWrongEvent,
			recentCompleted,
			recentInProgress,
			recentWaiting,
		},
	}

	cfg := &Config{
		GitHubAppID:             testAppID,
		GitHubAppInstallationID: testInstallID,
		GitHubAppPrivateKey:     testAppKey,
		GitHubOrg:               testOrg,
		GitHubRepo:              testRepo,
		WebhookID:               testWebhookID,
		Interval:                10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	assert.Equal(t, []int64{1, 4}, client.redelivered)

	m := mr.Collect(t)
	assert.Equal(t, 2.0, m.Counter(t, "github-runner.webhook.redelivery.count"))
	assert.Equal(t, 0.0, m.Counter(t, "github-runner.webhook.redelivery.errors"))
}

func TestRedeliverListError(t *testing.T) {
	/*
		arrange: Create a daemon whose GitHub client fails while listing deliveries.
		act: Run a single redelivery cycle.
		assert: No redeliveries are recorded and the redelivery error metric increases.
	*/
	mr := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	client := &fakeGitHubClient{
		listErr: fmt.Errorf("api error"),
	}

	cfg := &Config{
		GitHubAppID:             testAppID,
		GitHubAppInstallationID: testInstallID,
		GitHubAppPrivateKey:     testAppKey,
		GitHubOrg:               testOrg,
		WebhookID:               testWebhookID,
		Interval:                10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	m := mr.Collect(t)
	assert.Equal(t, 0.0, m.Counter(t, "github-runner.webhook.redelivery.count"))
	assert.Equal(t, 1.0, m.Counter(t, "github-runner.webhook.redelivery.errors"))
}

func TestRedeliverContinuesOnSingleFailure(t *testing.T) {
	/*
		arrange: Create a daemon with failed deliveries and a client that fails redelivery calls.
		act: Run a single redelivery cycle.
		assert: The cycle completes without recording successful redeliveries.
	*/
	_ = telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	now := time.Now().UTC()
	client := &fakeGitHubClient{
		deliveries: []*github.HookDelivery{
			makeDelivery(1, "failed", "workflow_job", "queued", now.Add(-1*time.Minute)),
			makeDelivery(2, "failed", "workflow_job", "queued", now.Add(-2*time.Minute)),
		},
		redeliverErr: fmt.Errorf("redeliver error"),
	}

	cfg := &Config{
		GitHubAppID:             testAppID,
		GitHubAppInstallationID: testInstallID,
		GitHubAppPrivateKey:     testAppKey,
		GitHubOrg:               testOrg,
		WebhookID:               testWebhookID,
		Interval:                10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	// Redelivery errors for individual deliveries are logged but don't stop the cycle.
	assert.Nil(t, client.redelivered)
}

func TestConfigValidation(t *testing.T) {
	/*
		arrange: Define configuration validation scenarios.
		act: Validate each configuration.
		assert: Expected validation errors are returned for invalid configs and none for valid configs.
	*/
	tests := []struct {
		name    string
		config  Config
		wantErr string
	}{
		{
			name:    "missing app id",
			config:  Config{GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org", WebhookID: 1},
			wantErr: "github app ID is required",
		},
		{
			name:    "app auth missing installation ID",
			config:  Config{GitHubAppID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org", WebhookID: 1},
			wantErr: "github app installation ID is required",
		},
		{
			name:    "app auth missing private key",
			config:  Config{GitHubAppID: 1, GitHubAppInstallationID: 1, GitHubOrg: "org", WebhookID: 1},
			wantErr: "github app private key is required",
		},
		{
			name:    "missing org",
			config:  Config{GitHubAppID: 1, GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", WebhookID: 1},
			wantErr: "github organisation is required",
		},
		{
			name:    "missing webhook ID",
			config:  Config{GitHubAppID: 1, GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org"},
			wantErr: "webhook ID is required",
		},
		{
			name:   "valid app auth",
			config: Config{GitHubAppID: 1, GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org", WebhookID: 1},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			/*
				arrange: Select one configuration scenario.
				act: Call Validate on the scenario config.
				assert: Error presence and content match expectations.
			*/
			err := tt.config.Validate()
			if tt.wantErr == "" {
				assert.NoError(t, err)
			} else {
				assert.ErrorContains(t, err, tt.wantErr)
			}
		})
	}
}

func TestDaemonStopsOnContextCancel(t *testing.T) {
	/*
		arrange: Create a daemon with a short interval and a context that times out.
		act: Run the daemon in a goroutine and wait for completion.
		assert: The daemon exits after context cancellation.
	*/
	_ = telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	client := &fakeGitHubClient{}
	cfg := &Config{
		GitHubAppID:             testAppID,
		GitHubAppInstallationID: testInstallID,
		GitHubAppPrivateKey:     testAppKey,
		GitHubOrg:               testOrg,
		WebhookID:               testWebhookID,
		Interval:                50 * time.Millisecond,
	}

	daemon := NewDaemonWithClient(cfg, client)

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	done := make(chan struct{})
	go func() {
		daemon.Run(ctx)
		close(done)
	}()

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("daemon did not stop after context cancellation")
	}
}
