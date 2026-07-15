/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package redelivery

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/bradleyfalzon/ghinstallation/v2"
	"github.com/google/go-github/v89/github"
)

// GitHubClient abstracts GitHub API operations for webhook delivery management.
type GitHubClient interface {
	ListDeliveries(ctx context.Context, org, repo string, hookID int64, since time.Time) ([]*github.HookDelivery, error)
	RedeliverDelivery(ctx context.Context, org, repo string, hookID, deliveryID int64) error
}

type githubClient struct {
	client *github.Client
}

func newGitHubClient(cfg *Config) (GitHubClient, error) {
	itr, err := ghinstallation.New(
		http.DefaultTransport,
		cfg.GitHubAppID,
		cfg.GitHubAppInstallationID,
		[]byte(cfg.GitHubAppPrivateKey),
	)
	if err != nil {
		return nil, fmt.Errorf("cannot create github app installation transport: %w", err)
	}
	client, err := github.NewClient(github.WithHTTPClient(&http.Client{Transport: itr}))
	if err != nil {
		return nil, fmt.Errorf("cannot create github client: %w", err)
	}
	return &githubClient{client: client}, nil
}

// ListDeliveries fetches hook deliveries newer than `since`, stopping pagination early
// once older deliveries are encountered.
func (g *githubClient) ListDeliveries(ctx context.Context, org, repo string, hookID int64, since time.Time) ([]*github.HookDelivery, error) {
	var allDeliveries []*github.HookDelivery
	opts := &github.ListCursorOptions{PerPage: 100}

	for {
		var deliveries []*github.HookDelivery
		var resp *github.Response
		var err error

		if repo != "" {
			deliveries, resp, err = g.client.Repositories.ListHookDeliveries(ctx, org, repo, hookID, opts)
		} else {
			deliveries, resp, err = g.client.Organizations.ListHookDeliveries(ctx, org, hookID, opts)
		}
		if err != nil {
			return nil, fmt.Errorf("cannot fetch hook deliveries: %w", err)
		}

		for _, d := range deliveries {
			if d.GetDeliveredAt().Time.Before(since) {
				return allDeliveries, nil
			}
			allDeliveries = append(allDeliveries, d)
		}

		if resp.Cursor == "" {
			break
		}
		opts.Cursor = resp.Cursor
	}

	return allDeliveries, nil
}

// RedeliverDelivery triggers redelivery of a specific hook delivery.
func (g *githubClient) RedeliverDelivery(ctx context.Context, org, repo string, hookID, deliveryID int64) error {
	var err error

	if repo != "" {
		_, _, err = g.client.Repositories.RedeliverHookDelivery(ctx, org, repo, hookID, deliveryID)
	} else {
		_, _, err = g.client.Organizations.RedeliverHookDelivery(ctx, org, hookID, deliveryID)
	}
	if err != nil {
		return fmt.Errorf("cannot redeliver hook delivery %d: %w", deliveryID, err)
	}

	return nil
}
