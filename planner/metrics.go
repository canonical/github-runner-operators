/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package planner provides observability to export prometheus metrics.
 */

package planner

import (
	"context"

	"github.com/prometheus/client_golang/prometheus"
)

const flavorPlatform = "github" // Currently only github is supported
const flavorPressureMetricName = "mayfly_planner_flavor_pressure"

// Metrics encapsulates all Prometheus metrics for the planner service.
type Metrics struct {
	flavorPressure *prometheus.GaugeVec
}

// NewMetrics creates and registers all planner metrics with the provided registry.
func NewMetrics(reg prometheus.Registerer) *Metrics {
	m := &Metrics{
		flavorPressure: prometheus.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: flavorPressureMetricName,
				Help: "The current pressure value for each flavor",
			},
			[]string{"platform", "flavor"},
		),
	}

	reg.MustRegister(m.flavorPressure)
	return m
}

// SetFlavorPressure updates the gauge value for a given platform and flavor.
func (m *Metrics) SetFlavorPressure(platform, flavor string, value float64) {
	m.flavorPressure.With(prometheus.Labels{
		"platform": platform,
		"flavor":   flavor,
	}).Set(value)
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
			m.flavorPressure.WithLabelValues(platform, flavor.Name).Set(float64(pressureValue))
		}
	}
	return nil
}
