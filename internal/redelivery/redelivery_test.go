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
	"github.com/google/go-github/v86/github"
	"github.com/stretchr/testify/assert"
)

const (
	testOrg       = "test-org"
	testRepo      = "test-repo"
	testWebhookID = int64(12345)
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
	mr := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	now := time.Now().UTC()
	recentFailed := makeDelivery(1, "failed", "workflow_job", "queued", now.Add(-2*time.Minute))
	recentOK := makeDelivery(2, "OK", "workflow_job", "queued", now.Add(-3*time.Minute))
	recentWrongEvent := makeDelivery(3, "failed", "push", "queued", now.Add(-4*time.Minute))
	recentWrongAction := makeDelivery(4, "failed", "workflow_job", "completed", now.Add(-5*time.Minute))

	client := &fakeGitHubClient{
		deliveries: []*github.HookDelivery{recentFailed, recentOK, recentWrongEvent, recentWrongAction},
	}

	cfg := &Config{
		GitHubToken: "test-token",
		GitHubOrg:   testOrg,
		GitHubRepo:  testRepo,
		WebhookID:   testWebhookID,
		Interval:    10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	assert.Equal(t, []int64{1, 4}, client.redelivered)

	m := mr.Collect(t)
	assert.Equal(t, 2.0, m.Counter(t, "github-runner.webhook.redelivery.count"))
	assert.Equal(t, 0.0, m.Counter(t, "github-runner.webhook.redelivery.errors"))
}

func TestRedeliverListError(t *testing.T) {
	mr := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	client := &fakeGitHubClient{
		listErr: fmt.Errorf("api error"),
	}

	cfg := &Config{
		GitHubToken: "test-token",
		GitHubOrg:   testOrg,
		WebhookID:   testWebhookID,
		Interval:    10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	m := mr.Collect(t)
	assert.Equal(t, 0.0, m.Counter(t, "github-runner.webhook.redelivery.count"))
	assert.Equal(t, 1.0, m.Counter(t, "github-runner.webhook.redelivery.errors"))
}

func TestRedeliverSkipsOKDeliveries(t *testing.T) {
	_ = telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	now := time.Now().UTC()
	client := &fakeGitHubClient{
		deliveries: []*github.HookDelivery{
			makeDelivery(1, "OK", "workflow_job", "queued", now.Add(-1*time.Minute)),
			makeDelivery(2, "OK", "workflow_job", "queued", now.Add(-2*time.Minute)),
		},
	}

	cfg := &Config{
		GitHubToken: "test-token",
		GitHubOrg:   testOrg,
		WebhookID:   testWebhookID,
		Interval:    10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	assert.Nil(t, client.redelivered)
}

func TestRedeliverContinuesOnSingleFailure(t *testing.T) {
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
		GitHubToken: "test-token",
		GitHubOrg:   testOrg,
		WebhookID:   testWebhookID,
		Interval:    10 * time.Minute,
	}

	daemon := NewDaemonWithClient(cfg, client)
	daemon.runOnce(context.Background())

	// Redelivery errors for individual deliveries are logged but don't stop the cycle.
	assert.Nil(t, client.redelivered)
}

func TestConfigValidation(t *testing.T) {
	tests := []struct {
		name    string
		config  Config
		wantErr string
	}{
		{
			name:    "missing auth",
			config:  Config{GitHubOrg: "org", WebhookID: 1},
			wantErr: "github authentication not configured",
		},
		{
			name:    "both auth methods",
			config:  Config{GitHubToken: "tok", GitHubAppID: 1, GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org", WebhookID: 1},
			wantErr: "github authentication is ambiguous",
		},
		{
			name:    "token auth with app installation details",
			config:  Config{GitHubToken: "tok", GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org", WebhookID: 1},
			wantErr: "github authentication is ambiguous",
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
			config:  Config{GitHubToken: "tok", WebhookID: 1},
			wantErr: "github organisation is required",
		},
		{
			name:    "missing webhook ID",
			config:  Config{GitHubToken: "tok", GitHubOrg: "org"},
			wantErr: "webhook ID is required",
		},
		{
			name:   "valid token auth",
			config: Config{GitHubToken: "tok", GitHubOrg: "org", WebhookID: 1},
		},
		{
			name:   "valid app auth",
			config: Config{GitHubAppID: 1, GitHubAppInstallationID: 1, GitHubAppPrivateKey: "key", GitHubOrg: "org", WebhookID: 1},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
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
	_ = telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	client := &fakeGitHubClient{}
	cfg := &Config{
		GitHubToken: "test-token",
		GitHubOrg:   testOrg,
		WebhookID:   testWebhookID,
		Interval:    50 * time.Millisecond,
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
