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
	lastFlavor   *database.Flavor
	tokenIsValid bool
	errToReturn  error
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

func (f *fakeStore) VerifyAuthToken(ctx context.Context, token [32]byte) (string, error) {
	if f.tokenIsValid {
		return "validTokenName", nil
	}
	return "", database.ErrNotExist
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

func TestCreateFlavor_shouldSucceed(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor via HTTP request
		assert: 201 response and flavor stored in fake store
	*/
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	body := `{"platform":"github","labels":["x64"],"priority":2}`
	req := newRequest(http.MethodPost, "/api/v1/flavors/runner-small", body, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusCreated, w.Code, "expected status 201")
	assert.Equal(t, "runner-small", store.lastFlavor.Name)
	assert.Equal(t, "github", store.lastFlavor.Platform)
}

func TestCreateFlavor_shouldSucceedWhenAlreadyExists(t *testing.T) {
	/*
		arrange: a store returning database.ErrExist and valid auth token
		act: create flavor via HTTP request
		assert: 201 response and flavor stored in fake store
	*/
	store := &fakeStore{errToReturn: database.ErrExist, tokenIsValid: true}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/existing-flavor", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("expected status 201, got %d", w.Code)
	}
	if store.lastFlavor.Name != "existing-flavor" {
		t.Errorf("expected flavor name 'existing-flavor', got %q", store.lastFlavor.Name)
	}
	if store.lastFlavor.Platform != "github" {
		t.Errorf("expected platform 'github', got %q", store.lastFlavor.Platform)
	}
}

func TestCreateFlavor_shouldFailOnInvalidJSON(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor with invalid JSON via HTTP request
		assert: 400 response
	*/
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/test", `{invalid-json}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid JSON, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailWhenNameMissing(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor without name via HTTP request
		assert: 404 response
	*/
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404 missing name, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailUnauthorizedWhenTokenInvalid(t *testing.T) {
	/*
		arrange: a fake store that invalidates tokens
		act: create flavor via HTTP request with invalid token
		assert: 401 response
	*/
	store := &fakeStore{tokenIsValid: false}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/test", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 Unauthorized, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailForNonPostMethod(t *testing.T) {
	/*
		arrange: a fake store that succeeds and valid auth token
		act: create flavor via HTTP GET request
		assert: 405 response
	*/
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, NewMetrics(store))
	token := makeToken()

	req := newRequest(http.MethodGet, "/api/v1/flavors/test", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405 for GET, got %d", w.Code)
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

	store := &fakeStore{tokenIsValid: true}
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
