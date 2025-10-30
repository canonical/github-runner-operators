/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit tests for the planner metrics subsystem.
 */

package planner

import (
	"context"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
)

// readGauge reads the current float value from a Prometheus Gauge.
func readGaugeValue(t *testing.T, g prometheus.Gauge) float64 {
	t.Helper()
	var m dto.Metric
	if err := g.Write(&m); err != nil {
		t.Fatalf("failed to read gauge: %v", err)
	}
	return m.GetGauge().GetValue()
}

// mockStore implements minimal FlavorStore behavior for tests.
type mockStore struct {
	listFlavors  func(ctx context.Context, platform string) ([]database.Flavor, error)
	getPressures func(ctx context.Context, platform string, flavors ...string) (map[string]int, error)
}

func (m *mockStore) ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error) {
	return m.listFlavors(ctx, platform)
}

func (m *mockStore) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	return m.getPressures(ctx, platform, flavors...)
}

func (m *mockStore) AddFlavor(ctx context.Context, flavor *database.Flavor) error {
	return nil
}

func (m *mockStore) VerifyAuthToken(ctx context.Context, token [32]byte) (string, error) {
	return "validTokenName", nil
}

func TestNewMetrics_shouldRegisterMetrics(t *testing.T) {
	// Given a planner metrics
	reg := prometheus.NewRegistry()
	m := NewMetrics(reg)

	// When setting a flavor pressure value
	m.SetFlavorPressure("github", "small", 5.0)
	metrics, err := reg.Gather()
	if err != nil {
		t.Fatalf("failed to gather metrics: %v", err)
	}

	// Then the metric should exist and contain our value
	found := false
	for _, mf := range metrics {
		if mf.GetName() != flavorPressureMetricName {
			continue
		}

		found = true
		if len(mf.GetMetric()) == 0 {
			t.Fatalf("flavor pressure metric has no data points")
		}

		got := mf.GetMetric()[0].GetGauge().GetValue()
		if got != 5.0 {
			t.Errorf("expected gauge value 5.0, got %v", got)
		}
	}
	if !found {
		t.Fatalf("flavor pressure metric not found in registry")
	}
}

func TestSetFlavorPressure_shouldCreateLabeledMetric(t *testing.T) {
	reg := prometheus.NewRegistry()
	m := NewMetrics(reg)

	// When setting values for multiple flavors
	m.SetFlavorPressure("github", "small", 1.0)
	m.SetFlavorPressure("github", "large", 3.5)

	metrics, err := reg.Gather()
	if err != nil {
		t.Fatalf("failed to gather metrics: %v", err)
	}

	count := 0
	for _, mf := range metrics {
		if mf.GetName() == flavorPressureMetricName {
			count += len(mf.GetMetric())
		}
	}

	// Then two labeled data points should exist
	if count != 2 {
		t.Errorf("expected 2 labeled metrics, got %d", count)
	}
}

func TestPopulateExistingFlavors_shouldSetGaugeValues(t *testing.T) {
	reg := prometheus.NewRegistry()
	m := NewMetrics(reg)

	store := &mockStore{
		listFlavors: func(ctx context.Context, platform string) ([]database.Flavor, error) {
			return []database.Flavor{
				{Name: "small", Platform: "github"},
				{Name: "medium", Platform: "github"},
			}, nil
		},
		getPressures: func(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
			return map[string]int{"small": 2, "medium": 5}, nil
		},
	}

	// When populating existing flavors
	err := m.PopulateExistingFlavors(context.Background(), store)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Then gauge values should be correctly set
	small := m.flavorPressure.WithLabelValues("github", "small")
	medium := m.flavorPressure.WithLabelValues("github", "medium")

	if got, want := readGaugeValue(t, small), 2.0; got != want {
		t.Errorf("small pressure = %v, want %v", got, want)
	}
	if got, want := readGaugeValue(t, medium), 5.0; got != want {
		t.Errorf("medium pressure = %v, want %v", got, want)
	}
}

func TestPopulateExistingFlavors_shouldDefaultToZeroWhenMissingPressure(t *testing.T) {
	reg := prometheus.NewRegistry()
	m := NewMetrics(reg)

	store := &mockStore{
		listFlavors: func(ctx context.Context, platform string) ([]database.Flavor, error) {
			return []database.Flavor{
				{Name: "large", Platform: "github"},
			}, nil
		},
		getPressures: func(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
			return map[string]int{}, nil // no pressures
		},
	}

	err := m.PopulateExistingFlavors(context.Background(), store)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	large := m.flavorPressure.WithLabelValues("github", "large")
	if got, want := readGaugeValue(t, large), 0.0; got != want {
		t.Errorf("large pressure = %v, want %v", got, want)
	}
}
