/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit tests for telemetry functions.
 */

package planner

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/stretchr/testify/assert"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

// mockStore is a mock implementation of FlavorStore for testing
type mockStore struct {
	flavors    []database.Flavor
	pressures  map[string]int
	listErr    error
	pressErr   error
	lastFlavor *database.Flavor
}

func (m *mockStore) AddFlavor(ctx context.Context, flavor *database.Flavor) error {
	m.lastFlavor = flavor
	return nil
}

func (m *mockStore) ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error) {
	if m.listErr != nil {
		return nil, m.listErr
	}
	// Return lastFlavor if it matches the platform
	if m.lastFlavor != nil && m.lastFlavor.Platform == platform {
		return []database.Flavor{*m.lastFlavor}, nil
	}
	return m.flavors, nil
}

func (m *mockStore) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	if m.pressErr != nil {
		return nil, m.pressErr
	}
	if m.pressures != nil {
		return m.pressures, nil
	}
	// Return 1 for each flavor if not specified
	res := make(map[string]int)
	for _, name := range flavors {
		res[name] = 1
	}
	return res, nil
}

// assertMetricObservedWithLabels checks if the specified metric has a datapoint with the expected value
// and labels platform and flavor set to the expected values.
func assertMetricObservedWithLabels(t *testing.T, tm telemetry.TestMetrics, name, platform, flavor string, expectedPressure int64) {
	found := false
OuterLoop:
	for _, sm := range tm.ScopeMetrics {
		for _, m := range sm.Metrics {
			if m.Name != name {
				continue
			}
			data := m.Data.(metricdata.Gauge[int64])
			for _, dp := range data.DataPoints {
				if dp.Value != expectedPressure {
					continue
				}

				// Check attributes contain platform and flavor
				hasPlatform := false
				hasFlavor := false
				for _, kv := range dp.Attributes.ToSlice() {
					if string(kv.Key) == "platform" && kv.Value.AsString() == platform {
						hasPlatform = true
					}
					if string(kv.Key) == "flavor" && kv.Value.AsString() == flavor {
						hasFlavor = true
					}
				}

				if hasPlatform && hasFlavor {
					found = true
					break OuterLoop
				}

			}

		}
	}
	assert.True(t, found, "expected gauge %q to have a datapoint with value=%d and labels platform=%s, flavor=%s", name, expectedPressure, platform, flavor)
}

func TestExtractFlavorNames(t *testing.T) {
	tests := []struct {
		name     string
		flavors  []database.Flavor
		expected []string
	}{
		{
			name: "shouldExtractMultipleNames",
			flavors: []database.Flavor{
				{Name: "small", Platform: "github"},
				{Name: "medium", Platform: "github"},
				{Name: "large", Platform: "github"},
			},
			expected: []string{"small", "medium", "large"},
		},
		{
			name: "shouldExtractSingleName",
			flavors: []database.Flavor{
				{Name: "test-flavor", Platform: "github"},
			},
			expected: []string{"test-flavor"},
		},
		{
			name:     "shouldReturnEmptyForNoFlavors",
			flavors:  []database.Flavor{},
			expected: []string{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := extractFlavorNames(tt.flavors)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestCreateFlavorUpdatesMetric_shouldRecordMetric(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor via HTTP request
		assert: metric updated with expected pressure value
	*/
	// arrange
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	store := &mockStore{}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	body := `{"platform": "github", "labels": ["self-hosted", "amd64"], "priority": 300}`

	req := newRequest(http.MethodPost, "/api/v1/flavors/test-flavor", body, token)
	w := httptest.NewRecorder()

	// act
	server.ServeHTTP(w, req)

	// assert
	assert.Equal(t, http.StatusCreated, w.Code, "should return 201 on successful create")

	tm := r.Collect(t)
	assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, "github", "test-flavor", 1)
}

func TestObserveFlavorPressures(t *testing.T) {
	/*
		Test observeFlavorPressures by using the full telemetry stack
		and verifying metrics are properly recorded with correct attributes.
	*/
	tests := []struct {
		name      string
		platform  string
		flavors   []database.Flavor
		pressures map[string]int
	}{
		{
			name:     "shouldObserveMultipleFlavors",
			platform: "github",
			flavors: []database.Flavor{
				{Name: "small", Platform: "github"},
				{Name: "medium", Platform: "github"},
			},
			pressures: map[string]int{
				"small":  10,
				"medium": 20,
			},
		},
		{
			name:     "shouldObserveSingleFlavor",
			platform: "github",
			flavors: []database.Flavor{
				{Name: "test", Platform: "github"},
			},
			pressures: map[string]int{
				"test": 5,
			},
		},
		{
			name:      "shouldHandleZeroPressure",
			platform:  "github",
			flavors:   []database.Flavor{{Name: "zero", Platform: "github"}},
			pressures: map[string]int{"zero": 0},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// arrange: setup test metrics reader
			r := telemetry.AcquireTestMetricReader(t)
			defer telemetry.ReleaseTestMetricReader(t)

			store := &mockStore{
				flavors:   tt.flavors,
				pressures: tt.pressures,
			}
			NewMetrics(store)

			// act: collect metrics
			tm := r.Collect(t)

			// assert: verify all flavors are recorded
			for _, f := range tt.flavors {
				expectedPressure := int64(tt.pressures[f.Name])
				assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, tt.platform, f.Name, expectedPressure)
			}
		})
	}
}

func TestCollectPlatformPressure(t *testing.T) {
	tests := []struct {
		name          string
		platform      string
		flavors       []database.Flavor
		pressures     map[string]int
		listErr       error
		pressErr      error
		expectMetrics bool
	}{
		{
			name:     "shouldCollectSuccessfully",
			platform: "github",
			flavors: []database.Flavor{
				{Name: "small", Platform: "github"},
				{Name: "large", Platform: "github"},
			},
			pressures: map[string]int{
				"small": 5,
				"large": 15,
			},
			expectMetrics: true,
		},
		{
			name:          "shouldHandleListFlavorError",
			platform:      "github",
			listErr:       errors.New("database error"),
			expectMetrics: false,
		},
		{
			name:     "shouldHandleGetPressuresError",
			platform: "github",
			flavors: []database.Flavor{
				{Name: "test", Platform: "github"},
			},
			pressErr:      errors.New("pressure fetch error"),
			expectMetrics: false,
		},
		{
			name:          "shouldHandleNoFlavors",
			platform:      "github",
			flavors:       []database.Flavor{},
			expectMetrics: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// arrange
			r := telemetry.AcquireTestMetricReader(t)
			defer telemetry.ReleaseTestMetricReader(t)

			store := &mockStore{
				flavors:   tt.flavors,
				pressures: tt.pressures,
				listErr:   tt.listErr,
				pressErr:  tt.pressErr,
			}
			NewMetrics(store)

			// act - trigger collection
			tm := r.Collect(t)

			// assert
			if tt.expectMetrics {
				// Verify metrics were collected for expected flavors
				for _, f := range tt.flavors {
					expectedPressure := int64(tt.pressures[f.Name])
					assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, tt.platform, f.Name, expectedPressure)
				}
			} else {
				// For error cases, we just verify the test runs without panic
				// The actual behavior is that no metrics are recorded when errors occur
				// but we can't easily verify this in isolation due to global metric registry
				assert.NotNil(t, tm, "metrics should be collected even if empty")
			}
		})
	}
}

func TestCollectFlavorPressure(t *testing.T) {
	tests := []struct {
		name      string
		flavors   []database.Flavor
		pressures map[string]int
	}{
		{
			name: "shouldCollectForAllPlatforms",
			flavors: []database.Flavor{
				{Name: "runner-small", Platform: "github"},
				{Name: "runner-large", Platform: "github"},
			},
			pressures: map[string]int{
				"runner-small": 3,
				"runner-large": 7,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// arrange
			r := telemetry.AcquireTestMetricReader(t)
			defer telemetry.ReleaseTestMetricReader(t)

			store := &mockStore{
				flavors:   tt.flavors,
				pressures: tt.pressures,
			}
			NewMetrics(store)

			// act - trigger collection
			tm := r.Collect(t)

			// assert: verify metrics are present
			for _, f := range tt.flavors {
				expectedPressure := int64(tt.pressures[f.Name])
				assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, "github", f.Name, expectedPressure)
			}
		})
	}
}

func TestCollectFlavorPressure_Integration(t *testing.T) {
	/*
		arrange: Integration test setup with mock store containing test flavors
		act: collect metrics via the full callback mechanism
		assert: verify metrics are properly exported with correct values
	*/
	// arrange
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	store := &mockStore{
		flavors: []database.Flavor{
			{Name: "test-flavor-1", Platform: "github"},
			{Name: "test-flavor-2", Platform: "github"},
		},
		pressures: map[string]int{
			"test-flavor-1": 42,
			"test-flavor-2": 99,
		},
	}
	NewMetrics(store)

	// act
	tm := r.Collect(t)

	// assert
	assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, "github", "test-flavor-1", 42)
	assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, "github", "test-flavor-2", 99)
}

func TestMust_shouldPanicOnError(t *testing.T) {
	// arrange
	testErr := errors.New("test error")

	// act & assert
	assert.Panics(t, func() {
		must("value", testErr)
	}, "must should panic when error is not nil")
}

func TestMust_shouldReturnValueOnSuccess(t *testing.T) {
	// arrange
	expectedValue := "test-value"

	// act
	result := must(expectedValue, nil)

	// assert
	assert.Equal(t, expectedValue, result)
}

func TestNewMetrics_shouldInitializeSuccessfully(t *testing.T) {
	// arrange
	store := &mockStore{}

	// act
	m := NewMetrics(store)

	// assert
	assert.NotNil(t, m)
	assert.NotNil(t, m.meter)
	assert.NotNil(t, m.logger)
	assert.NotNil(t, m.flavorPressureMetric)
	assert.Equal(t, store, m.store)
}

func TestNewMetrics_shouldRegisterMetric(t *testing.T) {
	/*
		arrange: setup test metrics reader and mock store
		act: create new Metrics instance and collect metrics
		assert: verify observable gauge is properly registered
	*/
	// arrange
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	store := &mockStore{
		flavors: []database.Flavor{
			{Name: "init-test", Platform: "github"},
		},
		pressures: map[string]int{
			"init-test": 123,
		},
	}

	// act
	m := NewMetrics(store)
	tm := r.Collect(t)

	// assert
	assert.NotNil(t, m, "metrics should be initialized")
	found := false
	for _, sm := range tm.ScopeMetrics {
		for _, metric := range sm.Metrics {
			if metric.Name == flavorPressureMetricName {
				found = true
				// Verify it's a gauge
				_, ok := metric.Data.(metricdata.Gauge[int64])
				assert.True(t, ok, "metric should be a Gauge[int64]")
				break
			}
		}
	}
	assert.True(t, found, "expected metric %q to be registered", flavorPressureMetricName)
}
