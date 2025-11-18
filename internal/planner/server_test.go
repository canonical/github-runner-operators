/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit tests for the planner server and telemetry.
 */

package planner

import (
	"bytes"
	"context"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"github.com/stretchr/testify/assert"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

type fakeStore struct {
	lastFlavor  *database.Flavor
	errToReturn error
}

func (f *fakeStore) AddFlavor(ctx context.Context, flavor *database.Flavor) error {
	f.lastFlavor = flavor
	return f.errToReturn
}

func (f *fakeStore) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	res := make(map[string]int)
	for _, name := range flavors {
		res[name] = 1
	}
	return res, nil
}

func (f *fakeStore) ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error) {
	if f.lastFlavor != nil && f.lastFlavor.Platform == platform {
		return []database.Flavor{*f.lastFlavor}, nil
	}
	return []database.Flavor{}, nil
}

func newRequest(method, url, body string, token string) *http.Request {
	req := httptest.NewRequest(method, url, bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	return req
}

func makeToken() string {
	b := make([]byte, 32)
	for i := range b {
		b[i] = byte(i)
	}
	return hex.EncodeToString(b)
}

func TestCreateFlavor(t *testing.T) {
	tests := []struct {
		name               string
		storeErr           error
		method             string
		url                string
		body               string
		expectedStatus     int
		expectedFlavorName string
		expectedPlatform   string
	}{
		{
			name:               "shouldSucceed",
			storeErr:           nil,
			method:             http.MethodPost,
			url:                "/api/v1/flavors/runner-small",
			body:               `{"platform":"github","labels":["x64"],"priority":2}`,
			expectedStatus:     http.StatusCreated,
			expectedFlavorName: "runner-small",
			expectedPlatform:   "github",
		},
		{
			name:               "shouldFailWhenAlreadyExists",
			storeErr:           database.ErrExist,
			method:             http.MethodPost,
			url:                "/api/v1/flavors/existing-flavor",
			body:               `{"platform":"github"}`,
			expectedStatus:     http.StatusConflict,
			expectedFlavorName: "existing-flavor",
			expectedPlatform:   "github",
		},
		{
			name:           "shouldFailOnInvalidJSON",
			storeErr:       nil,
			method:         http.MethodPost,
			url:            "/api/v1/flavors/test",
			body:           `{invalid-json}`,
			expectedStatus: http.StatusBadRequest,
		},
		{
			name:           "shouldFailWhenNameMissing",
			storeErr:       nil,
			method:         http.MethodPost,
			url:            "/api/v1/flavors/",
			body:           `{"platform":"github"}`,
			expectedStatus: http.StatusNotFound,
		},
		{
			name:           "shouldFailForNonPostMethod",
			storeErr:       nil,
			method:         http.MethodGet,
			url:            "/api/v1/flavors/test",
			body:           `{"platform":"github"}`,
			expectedStatus: http.StatusMethodNotAllowed,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{errToReturn: tt.storeErr}
			server := NewServer(store, NewMetrics(store))
			token := makeToken()

			req := newRequest(tt.method, tt.url, tt.body, token)
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)
			if tt.expectedFlavorName != "" {
				assert.Equal(t, tt.expectedFlavorName, store.lastFlavor.Name)
			}
			if tt.expectedPlatform != "" {
				assert.Equal(t, tt.expectedPlatform, store.lastFlavor.Platform)
			}
		})
	}
}

func TestCreateFlavorUpdatesMetric_shouldRecordMetric(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor via HTTP request
		assert: metric updated with expected pressure value
	*/
	// in-memory metrics
	r := telemetry.AcquireTestMetricReader(t)
	defer telemetry.ReleaseTestMetricReader(t)

	store := &fakeStore{}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	body := `{"platform": "github", "labels": ["self-hosted", "amd64"], "priority": 300}`

	req := newRequest(http.MethodPost, "/api/v1/flavors/test-flavor", body, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusCreated, w.Code, "should return 201 on successful create")

	// Collect and assert metric
	tm := r.Collect(t)
	assertMetricObservedWithLabels(t, tm, flavorPressureMetricName, "github", "test-flavor", 1)
}

// assertMetricObservedWithLabels checks if the specified metric has a datapoint with the expected value
// and labels platform and flavor set to the expected values.
func assertMetricObservedWithLabels(t *testing.T, tm telemetry.TestMetrics, name, platform, flavor string, expectedPressure int64) {
	found := false
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
					break
				}

			}

		}
	}
	assert.True(t, found, "expected gauge %q to have a datapoint with value=%d and labels platform=%s, flavor=%s", name, expectedPressure, platform, flavor)
}
