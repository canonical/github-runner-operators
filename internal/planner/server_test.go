/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit tests for the planner server.
 */

package planner

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/stretchr/testify/assert"
)

type fakeStore struct {
	pressures      atomic.Value
	lastFlavor     *database.Flavor
	errToReturn    error
	pressureChange chan struct{}
}

func (f *fakeStore) AddFlavor(ctx context.Context, flavor *database.Flavor) error {
	f.lastFlavor = flavor
	return f.errToReturn
}

func (f *fakeStore) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	pressures := f.pressures.Load()
	if pressures == nil {
		return map[string]int{}, nil
	}

	if len(flavors) == 0 {
		return pressures.(map[string]int), nil
	}
	res := make(map[string]int)
	for _, flavor := range flavors {
		if pressure, ok := pressures.(map[string]int)[flavor]; ok {
			res[flavor] = pressure
		}
	}
	return res, nil
}

func (f *fakeStore) ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error) {
	if f.lastFlavor != nil && f.lastFlavor.Platform == platform {
		return []database.Flavor{*f.lastFlavor}, nil
	}
	return []database.Flavor{}, nil
}

func (f *fakeStore) SubscribeToPressureUpdate(ctx context.Context) (<-chan struct{}, error) {
	return f.pressureChange, nil
}

func newRequest(method, url, body, token string) *http.Request {
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
	}{{
		name:               "shouldSucceed",
		storeErr:           nil,
		method:             http.MethodPost,
		url:                "/api/v1/flavors/runner-small",
		body:               `{"platform":"github","labels":["x64"],"priority":2}`,
		expectedStatus:     http.StatusCreated,
		expectedFlavorName: "runner-small",
		expectedPlatform:   "github",
	}, {
		name:               "shouldFailWhenAlreadyExists",
		storeErr:           database.ErrExist,
		method:             http.MethodPost,
		url:                "/api/v1/flavors/existing-flavor",
		body:               `{"platform":"github"}`,
		expectedStatus:     http.StatusConflict,
		expectedFlavorName: "existing-flavor",
		expectedPlatform:   "github",
	}, {
		name:           "shouldFailOnInvalidJSON",
		storeErr:       nil,
		method:         http.MethodPost,
		url:            "/api/v1/flavors/test",
		body:           `{invalid-json}`,
		expectedStatus: http.StatusBadRequest,
	}, {
		name:           "shouldFailWhenNameMissing",
		storeErr:       nil,
		method:         http.MethodPost,
		url:            "/api/v1/flavors/",
		body:           `{"platform":"github"}`,
		expectedStatus: http.StatusNotFound,
	}, {
		name:           "shouldFailForNonPostMethod",
		storeErr:       nil,
		method:         http.MethodGet,
		url:            "/api/v1/flavors/test",
		body:           `{"platform":"github"}`,
		expectedStatus: http.StatusMethodNotAllowed,
	}}

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

func TestGetFlavorPressure(t *testing.T) {
	tests := []struct {
		name              string
		pressures         map[string]int
		method            string
		url               string
		expectedStatus    int
		expectedPressures map[string]int
	}{{
		name:              "shouldSucceedForSingleFlavor",
		pressures:         map[string]int{"runner-small": 1, "runner-medium": 1, "runner-large": 1},
		method:            http.MethodGet,
		url:               "/api/v1/flavors/runner-small/pressure",
		expectedStatus:    http.StatusOK,
		expectedPressures: map[string]int{"runner-small": 1},
	}, {
		name:              "shouldSucceedForAllFlavors",
		pressures:         map[string]int{"runner-small": 1, "runner-medium": 1, "runner-large": 1},
		method:            http.MethodGet,
		url:               "/api/v1/flavors/_/pressure",
		expectedStatus:    http.StatusOK,
		expectedPressures: map[string]int{"runner-small": 1, "runner-medium": 1, "runner-large": 1},
	}, {
		name:           "shouldFailWhenFlavorNotExist",
		pressures:      map[string]int{"runner-medium": 1, "runner-large": 1},
		method:         http.MethodGet,
		url:            "/api/v1/flavors/runner-small/pressure",
		expectedStatus: http.StatusNotFound,
	}, {
		name:           "shouldFailWhenNameMissing",
		method:         http.MethodGet,
		url:            "/api/v1/flavors//pressure",
		expectedStatus: http.StatusMovedPermanently,
	}, {
		name:           "shouldFailForNonGetMethod",
		method:         http.MethodPost,
		url:            "/api/v1/flavors/runner-small/pressure",
		expectedStatus: http.StatusMethodNotAllowed,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pressures := atomic.Value{}
			pressures.Store(tt.pressures)
			store := &fakeStore{pressures: pressures}
			server := NewServer(store, NewMetrics(store))
			token := makeToken()

			req := newRequest(tt.method, tt.url, "", token)
			w := httptest.NewRecorder()
			server.ServeHTTP(w, req)

			var resp map[string]int
			json.NewDecoder(w.Body).Decode(&resp)

			assert.Equal(t, tt.expectedStatus, w.Code)
			assert.Equal(t, tt.expectedPressures, resp)
		})
	}
}

func TestGetFlavorPressureStream(t *testing.T) {
	tests := []struct {
		name                    string
		pressuresStream         []map[string]int
		method                  string
		url                     string
		expectedStatus          []int
		expectedPressuresStream []map[string]int
	}{{
		name: "shouldSucceedForSingleFlavor",
		pressuresStream: []map[string]int{
			{"runner-small": 1, "runner-large": 2},
			{"runner-small": 2, "runner-large": 3},
			{"runner-small": 3, "runner-large": 1},
		},
		method:         http.MethodGet,
		url:            "/api/v1/flavors/runner-small/pressure?stream=true",
		expectedStatus: []int{http.StatusOK, http.StatusOK, http.StatusOK},
		expectedPressuresStream: []map[string]int{
			{"runner-small": 1},
			{"runner-small": 2},
			{"runner-small": 3},
		},
	}, {
		name:                    "shouldSucceedForAllFlavors",
		pressuresStream:         []map[string]int{{"runner-small": 1, "runner-large": 2}, {"runner-small": 3, "runner-large": 4}, {"runner-small": 5, "runner-large": 6}},
		method:                  http.MethodGet,
		url:                     "/api/v1/flavors/_/pressure?stream=true",
		expectedStatus:          []int{http.StatusOK, http.StatusOK, http.StatusOK},
		expectedPressuresStream: []map[string]int{{"runner-small": 1, "runner-large": 2}, {"runner-small": 3, "runner-large": 4}, {"runner-small": 5, "runner-large": 6}},
	}, {
		name:                    "shouldFailWhenFlavorNotExist",
		pressuresStream:         []map[string]int{{"runner-medium": 2, "runner-large": 1}},
		method:                  http.MethodGet,
		url:                     "/api/v1/flavors/runner-small/pressure?stream=true",
		expectedStatus:          []int{http.StatusNotFound},
		expectedPressuresStream: []map[string]int{nil},
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pressures := atomic.Value{}
			pressures.Store(tt.pressuresStream[0])
			store := &fakeStore{pressures: pressures, pressureChange: make(chan struct{}, 10)}
			server := NewServer(store, NewMetrics(store))

			ts := httptest.NewUnstartedServer(server)
			ts.EnableHTTP2 = true
			ts.StartTLS()
			defer ts.Close()

			resp, err := ts.Client().Get(ts.URL + tt.url)
			assert.NoError(t, err)
			defer resp.Body.Close()

			var res map[string]int
			json.NewDecoder(resp.Body).Decode(&res)

			assert.Equal(t, tt.expectedStatus[0], resp.StatusCode)
			assert.Equal(t, tt.expectedPressuresStream[0], res)
			for i := range len(tt.pressuresStream[1:]) - 1 {
				store.pressures.Store(tt.pressuresStream[i+1])
				store.pressureChange <- struct{}{}

				json.NewDecoder(resp.Body).Decode(&res)
				assert.Equal(t, tt.expectedStatus[i+1], resp.StatusCode)
				assert.Equal(t, tt.expectedPressuresStream[i+1], res)
			}
		})
	}
}

func TestHealth(t *testing.T) {
	store := &fakeStore{}
	server := NewServer(store, NewMetrics(store))

	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, "application/json", w.Header().Get("Content-Type"))

	var resp map[string]string
	err := json.NewDecoder(w.Body).Decode(&resp)
	assert.NoError(t, err)
	assert.Equal(t, "ok", resp["status"])
}
