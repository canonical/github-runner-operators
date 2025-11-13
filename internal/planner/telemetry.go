package planner

import (
	"context"
	"sync"

	"github.com/canonical/github-runner-operators/internal/telemetry"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
)

const (
	flavorPlatform           = "github" // Currently only github is supported
	flavorPressureMetricName = "mayfly_planner_flavor_pressure"
)

// must is a helper function that panics if an error is encountered, else returns the object.
func must[T any](obj T, err error) T {
	if err != nil {
		panic(err)
	}
	return obj
}

var (
	pkg                  = "github.com/canonical/github-runner-operators/internal/planner"
	meter                = otel.Meter(pkg)
	logger               = telemetry.NewLogger(pkg)
	flavorPressureMetric = must(
		meter.Int64ObservableGauge(
			flavorPressureMetricName,
			metric.WithDescription("The current pressure value for each flavor"),
			metric.WithUnit("{pressure}"),
		),
	)
)

// Metrics encapsulates all OpenTelemetry metrics for the planner service.
type Metrics struct {
	mu    sync.RWMutex
	store FlavorStore
}

// NewMetrics initializes the planner metrics and registers the observable gauge.
func NewMetrics(store FlavorStore) *Metrics {
	m := &Metrics{
		store: store,
	}

	must(
		meter.RegisterCallback(
			func(ctx context.Context, observer metric.Observer) error {
				m.mu.RLock()
				defer m.mu.RUnlock()

				// Pressure value is read directly from database at collection time
				// Performance should not be an issue since metrics scraping typically occurs every 5-60 seconds.
				platforms := []string{flavorPlatform}
				for _, platform := range platforms {
					flavors, err := m.store.ListFlavors(ctx, platform)
					if err != nil {
						logger.ErrorContext(ctx, "failed to list flavors for metrics", "platform", platform, "error", err)
						continue
					}
					if len(flavors) == 0 {
						continue
					}
					names := make([]string, 0, len(flavors))
					for _, f := range flavors {
						names = append(names, f.Name)
					}
					pressures, err := m.store.GetPressures(ctx, platform, names...)
					if err != nil {
						logger.ErrorContext(ctx, "failed to get pressures for metrics", "platform", platform, "error", err)
						continue
					}
					for _, f := range flavors {
						v := pressures[f.Name]
						observer.ObserveInt64(
							flavorPressureMetric,
							int64(v),
							metric.WithAttributes(
								attribute.String("platform", platform),
								attribute.String("flavor", f.Name),
							),
						)
					}
				}
				return nil
			},
			flavorPressureMetric,
		),
	)

	return m
}
