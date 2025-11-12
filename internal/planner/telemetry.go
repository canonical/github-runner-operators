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
	mu        sync.RWMutex
	pressures map[[2]string]int64 // key is [platform, flavor]
}

// NewMetrics initializes the planner metrics and registers the observable gauge.
func NewMetrics() *Metrics {
	m := &Metrics{
		pressures: make(map[[2]string]int64),
	}

	must(
		meter.RegisterCallback(
			func(_ context.Context, observer metric.Observer) error {
				m.mu.RLock()
				defer m.mu.RUnlock()

				for key, value := range m.pressures {
					platform, flavor := key[0], key[1]
					observer.ObserveInt64(
						flavorPressureMetric,
						value,
						metric.WithAttributes(
							attribute.String("platform", platform),
							attribute.String("flavor", flavor),
						),
					)
				}
				return nil
			},
			flavorPressureMetric,
		),
	)

	return m
}

// ObserveFlavorPressure updates the gauge value for a given platform and flavor.
func (m *Metrics) ObserveFlavorPressure(platform, flavor string, value int64) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.pressures[[2]string{platform, flavor}] = value
}

// PopulateExistingFlavors initializes the flavor pressure gauge with existing flavors from the database.
func (m *Metrics) PopulateExistingFlavors(ctx context.Context, store FlavorStore) error {
	platforms := []string{flavorPlatform}
	for _, platform := range platforms {
		// Get all flavors for the platform
		flavors, err := store.ListFlavors(ctx, platform)
		if err != nil {
			return err
		}
		if len(flavors) == 0 {
			continue
		}

		// Extract flavor names
		flavorNames := make([]string, 0, len(flavors))
		for _, flavor := range flavors {
			flavorNames = append(flavorNames, flavor.Name)
		}

		// Get pressures for the flavors
		pressures, err := store.GetPressures(ctx, platform, flavorNames...)
		if err != nil {
			return err
		}

		// Set gauge labels in the format (platform, flavor) with pressure value
		for _, flavor := range flavors {
			pressureValue, ok := pressures[flavor.Name]
			if !ok {
				pressureValue = 0
			}
			m.ObserveFlavorPressure(platform, flavor.Name, int64(pressureValue))
		}
	}

	logger.Info("initialized flavor pressure metrics", "entries", len(m.pressures))
	return nil
}
