/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit and scenario tests for telemetry functions.
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

// mockStore implements FlavorStore for tests.
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
	res := make(map[string]int)
	for _, f := range flavors {
		res[f] = 1
	}
	return res, nil
}

func (m *mockStore) CreateAuthToken(ctx context.Context, name string) ([32]byte, error) {
	return [32]byte{}, nil
}

func (m *mockStore) DeleteAuthToken(ctx context.Context, name string) error {
	return nil
}

// assertMetricObservedWithLabels asserts the gauge has a datapoint matching flavor + platform + value.
func assertMetricObservedWithLabels(t *testing.T, tm telemetry.TestMetrics, name, platform, flavor string, expectedPressure int64) {
	t.Helper()
	found := false

Outer:
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
				hasPlatform, hasFlavor := false, false
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
					break Outer
				}
			}
		}
	}
	assert.True(t, found, "expected gauge %q to have value=%d platform=%s flavor=%s", name, expectedPressure, platform, flavor)
}

// collectAndAssertPressures DRYs the reader → metrics → collect → assert loop.
func collectAndAssertPressures(t *testing.T, store *mockStore, expected map[string]int, platform string) {
	t.Helper()
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	NewMetrics(store)

	tm := r.Collect(t)
	for f, v := range expected {
		assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, platform, f, int64(v))
	}
}

func TestCreateFlavorUpdatesMetric_shouldRecordMetric(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor via HTTP request
		assert: metric updated with expected pressure value
	*/
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	store := &mockStore{}
	server := NewServer(store, store, NewMetrics(store), "planner_v0_test_admin_token__01")
	token := makeToken()

	body := `{"platform":"github","labels":["self-hosted","amd64"],"priority":300}`
	req := newRequest(http.MethodPost, "/api/v1/flavors/test-flavor", body, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusCreated, w.Code)
	tm := r.Collect(t)
	assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, "github", "test-flavor", 1)
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

func TestMetrics_SuccessScenarios(t *testing.T) {
	cases := []struct {
		name      string
		flavors   []database.Flavor
		pressures map[string]int
	}{
		{
			name: "shouldObserveMultipleFlavors",
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
			name: "shouldObserveSingleFlavor",
			flavors: []database.Flavor{
				{Name: "test", Platform: "github"},
			},
			pressures: map[string]int{
				"test": 5,
			},
		},
		{
			name:      "shouldHandleZeroPressure",
			flavors:   []database.Flavor{{Name: "zero", Platform: "github"}},
			pressures: map[string]int{"zero": 0},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			collectAndAssertPressures(t, &mockStore{flavors: c.flavors, pressures: c.pressures}, c.pressures, "github")
		})
	}
}

func TestMetrics_ErrorCases(t *testing.T) {
	cases := []struct {
		name      string
		flavors   []database.Flavor
		pressures map[string]int
		listErr   error
		pressErr  error
	}{
		{
			name:    "shouldHandleListFlavorError",
			listErr: errors.New("list error"),
		},
		{
			name:     "shouldHandleGetPressuresError",
			flavors:  []database.Flavor{{Name: "x", Platform: "github"}},
			pressErr: errors.New("press error"),
		},
		{
			name:    "shouldHandleNoFlavors",
			flavors: []database.Flavor{},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := telemetry.AcquireTestMetricReader(t)
			defer telemetry.ReleaseTestMetricReader(t)
			store := &mockStore{flavors: c.flavors, pressures: c.pressures, listErr: c.listErr, pressErr: c.pressErr}
			NewMetrics(store)
			_ = r.Collect(t) // ensure no panic; absence of metrics acceptable
		})
	}
}

func TestMust(t *testing.T) {
	cases := []struct {
		name        string
		val         string
		err         error
		shouldPanic bool
	}{
		{name: "panic", val: "ignored", err: errors.New("boom"), shouldPanic: true},
		{name: "noPanic", val: "ok", err: nil, shouldPanic: false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if c.shouldPanic {
				assert.Panics(t, func() { must(c.val, c.err) })
			} else {
				assert.Equal(t, c.val, must(c.val, c.err))
			}
		})
	}
}

func TestNewMetricsInitialization(t *testing.T) {
	/*
		arrange: a mock store
		act: initialize metrics
		assert: metrics initialized without error, gauge registered
	*/
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	store := &mockStore{
		flavors:   []database.Flavor{{Name: "init", Platform: "github"}},
		pressures: map[string]int{"init": 2},
	}

	NewMetrics(store)
	tm := r.Collect(t)

	found := false
	for _, sm := range tm.ScopeMetrics {
		for _, metric := range sm.Metrics {
			if metric.Name == flavorPressureMetricName {
				_, ok := metric.Data.(metricdata.Gauge[int64])
				assert.True(t, ok)
				found = true
				break
			}
		}
	}
	assert.True(t, found, "gauge should be registered")
}
