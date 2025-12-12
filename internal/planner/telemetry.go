/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package planner provides OpenTelemetry metrics for the planner service.
 */

package planner

import (
	"context"
	"sync"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/google/go-github/v80/github"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

const (
	flavorPressureMetricName        = "github-runner.planner.flavor.pressure"
	webhookErrorsMetricName         = "github-runner.planner.webhook.errors"
	processedWebhooksMetricName     = "github-runner.planner.webhook.processed"
	discardedWebhooksMetricName     = "github-runner.planner.webhook.discarded"
	webhookJobWaitingTimeMetricName = "github-runner.planner.webhook.job.waiting"
	webhookJobRunningTimeMetricName = "github-runner.planner.webhook.job.running"
)

// must is a helper function that panics if an error is encountered, else returns the object.
func must[T any](obj T, err error) T {
	if err != nil {
		panic(err)
	}
	return obj
}

var (
	pkg    = "github.com/canonical/github-runner-operators/internal/planner"
	logger = telemetry.NewLogger(pkg)
	trace  = otel.Tracer(pkg)
)

// Metrics encapsulates all OpenTelemetry metrics for the planner service.
type Metrics struct {
	mu    sync.RWMutex
	store FlavorStore
	meter metric.Meter

	flavorPressure        metric.Int64ObservableGauge
	webhookErrors         metric.Int64Counter
	processedWebhooks     metric.Int64Counter
	discardedWebhooks     metric.Int64Counter
	webhookJobWaitingTime metric.Float64Histogram
	webhookJobRunningTime metric.Float64Histogram
}

// NewMetrics initializes the planner metrics and registers the observable gauge.
func NewMetrics(store FlavorStore) *Metrics {
	m := &Metrics{
		store: store,
		meter: otel.Meter(pkg),
	}

	m.flavorPressure = must(
		m.meter.Int64ObservableGauge(
			flavorPressureMetricName,
			metric.WithDescription("The current pressure value for each flavor"),
			metric.WithUnit("{pressure}"),
		),
	)
	m.webhookErrors = must(
		m.meter.Int64Counter(
			webhookErrorsMetricName,
			metric.WithDescription("Total number of webhook processing errors"),
			metric.WithUnit("{error}"),
		),
	)
	m.discardedWebhooks = must(
		m.meter.Int64Counter(
			discardedWebhooksMetricName,
			metric.WithDescription("Total number of discarded webhooks"),
			metric.WithUnit("{webhook}"),
		),
	)
	m.processedWebhooks = must(
		m.meter.Int64Counter(
			processedWebhooksMetricName,
			metric.WithDescription("Total number of processed received"),
			metric.WithUnit("{webhook}"),
		),
	)
	jobDurationBucket := metric.WithExplicitBucketBoundaries(
		0,
		30,
		60,
		2*60,
		3*60,
		5*60,
		7.5*60,
		10*60,
		15*60,
		20*60,
		25*60,
		30*60,
		40*60,
		50*60,
		60*60,
		80*60,
		100*60,
		120*60,
		150*60,
		180*60,
		240*60,
		300*60,
		360*60,
	)
	m.webhookJobWaitingTime = must(
		m.meter.Float64Histogram(
			webhookJobWaitingTimeMetricName,
			metric.WithDescription("Histogram of job waiting times from webhook reception to job start"),
			metric.WithUnit("s"),
			jobDurationBucket,
		),
	)
	m.webhookJobRunningTime = must(
		m.meter.Float64Histogram(
			webhookJobRunningTimeMetricName,
			metric.WithDescription("Histogram of job running times from job start to job completion"),
			metric.WithUnit("s"),
			jobDurationBucket,
		),
	)

	must(
		m.meter.RegisterCallback(
			m.collectFlavorPressure,
			m.flavorPressure,
		),
	)

	return m
}

// collectFlavorPressure collects flavor pressure metrics for all platforms.
func (m *Metrics) collectFlavorPressure(ctx context.Context, observer metric.Observer) error {
	m.mu.RLock()
	defer m.mu.RUnlock()

	// Pressure value is read directly from database at collection time
	// Performance should not be an issue since metrics scraping typically occurs every 5-60 seconds.
	platforms := []string{flavorPlatform}
	for _, platform := range platforms {
		m.collectPlatformPressure(ctx, observer, platform)
	}
	return nil
}

// collectPlatformPressure collects flavor pressure metrics for a single platform.
func (m *Metrics) collectPlatformPressure(ctx context.Context, observer metric.Observer, platform string) {
	flavors, err := m.store.ListFlavors(ctx, platform)
	if err != nil {
		logger.ErrorContext(ctx, "failed to list flavors for metrics", "platform", platform, "error", err)
		return
	}

	if len(flavors) == 0 {
		return
	}

	flavorNames := extractFlavorNames(flavors)
	pressures, err := m.store.GetPressures(ctx, platform, flavorNames...)
	if err != nil {
		logger.ErrorContext(ctx, "failed to get pressures for metrics", "platform", platform, "error", err)
		return
	}

	m.observeFlavorPressures(observer, platform, flavors, pressures)
}

// extractFlavorNames extracts the names from a list of flavors.
func extractFlavorNames(flavors []database.Flavor) []string {
	names := make([]string, 0, len(flavors))
	for _, f := range flavors {
		names = append(names, f.Name)
	}
	return names
}

// observeFlavorPressures records pressure observations for each flavor.
func (m *Metrics) observeFlavorPressures(observer metric.Observer, platform string, flavors []database.Flavor, pressures map[string]int) {
	for _, f := range flavors {
		v := pressures[f.Name]
		observer.ObserveInt64(
			m.flavorPressure,
			int64(v),
			metric.WithAttributes(
				attribute.String("platform", platform),
				attribute.String("flavor", f.Name),
			),
		)
	}
}

func (m *Metrics) ObserveWebhookError(ctx context.Context, platform string) {
	m.webhookErrors.Add(ctx, 1, metric.WithAttributes(attribute.String("platform", platform)))
}

func (m *Metrics) ObserveDiscardedWebhook(ctx context.Context, platform string) {
	m.discardedWebhooks.Add(ctx, 1, metric.WithAttributes(attribute.String("platform", platform)))
}

func (m *Metrics) ObserveProcessedGitHubWebhook(ctx context.Context, webhook *github.WorkflowJobEvent) {
	attributes := metric.WithAttributes(attribute.String("platform", "github"), attribute.String("event", webhook.GetAction()))
	if webhook.WorkflowJob == nil {
		return
	}
	m.processedWebhooks.Add(ctx, 1, attributes)
	if webhook.WorkflowJob.CompletedAt != nil && webhook.WorkflowJob.StartedAt != nil {
		runningTime := webhook.WorkflowJob.CompletedAt.Sub(webhook.WorkflowJob.StartedAt.Time).Seconds()
		m.webhookJobRunningTime.Record(ctx, runningTime, attributes)
	} else if webhook.WorkflowJob.StartedAt != nil && webhook.WorkflowJob.CreatedAt != nil {
		waitingTime := webhook.WorkflowJob.StartedAt.Sub(webhook.WorkflowJob.CreatedAt.Time).Seconds()
		m.webhookJobWaitingTime.Record(ctx, waitingTime, attributes)
	}
}
