/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package planner provides OpenTelemetry metrics for the planner service.
 */

package planner

import (
	"context"
	"log/slog"
	"sync"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

const flavorPressureMetricName = "mayfly_planner_flavor_pressure"

// must is a helper function that panics if an error is encountered, else returns the object.
func must[T any](obj T, err error) T {
	if err != nil {
		panic(err)
	}
	return obj
}

var (
	pkg = "github.com/canonical/github-runner-operators/internal/planner"
)

// Metrics encapsulates all OpenTelemetry metrics for the planner service.
type Metrics struct {
	mu                   sync.RWMutex
	store                FlavorStore
	meter                metric.Meter
	logger               *slog.Logger
	flavorPressureMetric metric.Int64ObservableGauge
}

// NewMetrics initializes the planner metrics and registers the observable gauge.
func NewMetrics(store FlavorStore) *Metrics {
	m := &Metrics{
		store:  store,
		meter:  otel.Meter(pkg),
		logger: telemetry.NewLogger(pkg),
	}

	m.flavorPressureMetric = must(
		m.meter.Int64ObservableGauge(
			flavorPressureMetricName,
			metric.WithDescription("The current pressure value for each flavor"),
			metric.WithUnit("{pressure}"),
		),
	)

	must(
		m.meter.RegisterCallback(
			m.collectFlavorPressure,
			m.flavorPressureMetric,
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
		m.logger.ErrorContext(ctx, "failed to list flavors for metrics", "platform", platform, "error", err)
		return
	}

	if len(flavors) == 0 {
		return
	}

	flavorNames := extractFlavorNames(flavors)
	pressures, err := m.store.GetPressures(ctx, platform, flavorNames...)
	if err != nil {
		m.logger.ErrorContext(ctx, "failed to get pressures for metrics", "platform", platform, "error", err)
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
			m.flavorPressureMetric,
			int64(v),
			metric.WithAttributes(
				attribute.String("platform", platform),
				attribute.String("flavor", f.Name),
			),
		)
	}
}
