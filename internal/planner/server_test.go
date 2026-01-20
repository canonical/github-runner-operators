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
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type fakeStore struct {
	pressures      atomic.Value
	lastFlavor     *database.Flavor
	errToReturn    error
	pressureChange chan struct{}

	// Auth token controls
	createTokErr error
	deleteTokErr error

	nameToToken map[string][32]byte
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

	pressureMap, ok := pressures.(map[string]int)
	if !ok {
		return nil, fmt.Errorf("invalid pressure data type")
	}

	if len(flavors) == 0 {
		return pressureMap, nil
	}
	res := make(map[string]int)
	for _, flavor := range flavors {
		if pressure, ok := pressureMap[flavor]; ok {
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

func (f *fakeStore) GetFlavor(ctx context.Context, name string) (*database.Flavor, error) {
	if f.errToReturn == nil {
		return f.lastFlavor, nil
	}
	return nil, f.errToReturn
}

func (f *fakeStore) UpdateFlavor(ctx context.Context, flavor *database.Flavor) error {
	f.lastFlavor = flavor
	return f.errToReturn
}

func (f *fakeStore) DeleteFlavor(ctx context.Context, platform, name string) error {
	f.lastFlavor = nil
	return f.errToReturn
}

// AuthStore methods
func (f *fakeStore) CreateAuthToken(ctx context.Context, name string) ([32]byte, error) {
	if f.createTokErr != nil {
		return [32]byte{}, f.createTokErr
	}
	// Initialize maps on first use
	if f.nameToToken == nil {
		f.nameToToken = make(map[string][32]byte)
	}
	// Return preloaded token if present; else create a zero token entry
	if tok, ok := f.nameToToken[name]; ok {
		return tok, nil
	}
	var tok [32]byte
	f.nameToToken[name] = tok
	return tok, nil
}

func (f *fakeStore) DeleteAuthToken(ctx context.Context, name string) error {
	if f.deleteTokErr != nil {
		return f.deleteTokErr
	}
	if f.nameToToken == nil {
		return database.ErrNotExist
	}
	_, ok := f.nameToToken[name]
	if !ok {
		return database.ErrNotExist
	}
	delete(f.nameToToken, name)
	return nil
}

func (f *fakeStore) VerifyAuthToken(ctx context.Context, token [32]byte) (string, error) {
	if f.nameToToken == nil {
		return "", database.ErrNotExist
	}
	for name, tok := range f.nameToToken {
		if tok == token {
			return name, nil
		}
	}
	return "", database.ErrNotExist
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

func TestCreateFlavor(t *testing.T) {
	tests := []struct {
		name               string
		storeErr           error
		url                string
		body               string
		expectedStatus     int
		expectedFlavorName string
		expectedPlatform   string
	}{{
		name:               "shouldSucceed",
		storeErr:           nil,
		url:                "/api/v1/flavors/runner-small",
		body:               `{"platform":"github","labels":["x64"],"priority":2}`,
		expectedStatus:     http.StatusCreated,
		expectedFlavorName: "runner-small",
		expectedPlatform:   "github",
	}, {
		name:               "shouldFailWhenAlreadyExists",
		storeErr:           database.ErrExist,
		url:                "/api/v1/flavors/existing-flavor",
		body:               `{"platform":"github"}`,
		expectedStatus:     http.StatusConflict,
		expectedFlavorName: "existing-flavor",
		expectedPlatform:   "github",
	}, {
		name:           "shouldFailOnInvalidJSON",
		storeErr:       nil,
		url:            "/api/v1/flavors/test",
		body:           `{invalid-json}`,
		expectedStatus: http.StatusBadRequest,
	}, {
		name:           "shouldFailWhenNameMissing",
		storeErr:       nil,
		url:            "/api/v1/flavors/",
		body:           `{"platform":"github"}`,
		expectedStatus: http.StatusNotFound,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{errToReturn: tt.storeErr}
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(http.MethodPost, tt.url, tt.body, adminToken)
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

func TestGetFlavor(t *testing.T) {
	tests := []struct {
		name           string
		storeFlavor    *database.Flavor
		storeErr       error
		url            string
		expectedStatus int
		assertFlavor   bool
	}{{
		name: "shouldSucceed",
		storeFlavor: &database.Flavor{
			Platform:        "github",
			Name:            "runner-small",
			Labels:          []string{"x64"},
			Priority:        10,
			IsDisabled:      false,
			MinimumPressure: 5,
		},
		url:            "/api/v1/flavors/runner-small",
		expectedStatus: http.StatusOK,
		assertFlavor:   true,
	}, {
		name:           "shouldFailWhenFlavorMissing",
		storeErr:       database.ErrNotExist,
		url:            "/api/v1/flavors/non-existent-flavor",
		expectedStatus: http.StatusNotFound,
	}, {
		name:           "shouldFailWhenNameIsAllFlavors",
		storeErr:       database.ErrNotExist,
		url:            "/api/v1/flavors/_",
		expectedStatus: http.StatusNotFound,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{lastFlavor: tt.storeFlavor, errToReturn: tt.storeErr}
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(http.MethodGet, tt.url, "", adminToken)
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)
			if tt.assertFlavor {
				flavor := &database.Flavor{}
				require.NoError(t, json.NewDecoder(w.Body).Decode(flavor))
				storedFlavor, err := store.GetFlavor(t.Context(), tt.storeFlavor.Name)
				require.NoError(t, err)
				assert.Equal(t, flavor, storedFlavor)
			}
		})
	}
}

func TestUpdateFlavor(t *testing.T) {
	tests := []struct {
		name           string
		storeFlavor    *database.Flavor
		storeErr       error
		url            string
		body           string
		expectedStatus int
		assertFlavor   bool
	}{{
		name: "shouldSucceed",
		storeFlavor: &database.Flavor{
			Platform:        "github",
			Name:            "runner-small",
			Labels:          []string{"x64"},
			Priority:        10,
			IsDisabled:      false,
			MinimumPressure: 5,
		},
		url:            "/api/v1/flavors/runner-small",
		body:           `{"platform":"github","name":"runner-small","labels":["x64"],"priority":5,"is_disabled":false,"minimum_pressure":10}`,
		expectedStatus: http.StatusOK,
		assertFlavor:   true,
	}, {
		name:           "shouldFailWhenFlavorMissing",
		storeErr:       database.ErrNotExist,
		url:            "/api/v1/flavors/not-exist",
		body:           `{"platform":"github","name":"not-exist","labels":["x64"],"priority":5,"is_disabled":false,"minimum_pressure":10}`,
		expectedStatus: http.StatusNotFound,
		assertFlavor:   false,
	}, {
		name: "shouldFailWhenNameIsAllFlavors",
		storeFlavor: &database.Flavor{
			Platform:        "github",
			Name:            "runner-small",
			Labels:          []string{"x64"},
			Priority:        10,
			IsDisabled:      false,
			MinimumPressure: 5,
		},
		url:            "/api/v1/flavors/_",
		body:           `{"platform":"github","name":"not-exist","labels":["x64"],"priority":5,"is_disabled":false,"minimum_pressure":10}`,
		expectedStatus: http.StatusBadRequest,
	}, {
		name: "shouldFailOnInvalidJSON",
		storeFlavor: &database.Flavor{
			Platform:        "github",
			Name:            "runner-small",
			Labels:          []string{"x64"},
			Priority:        10,
			IsDisabled:      false,
			MinimumPressure: 5,
		},
		url:            "/api/v1/flavors/runner-small",
		body:           `{invalid-json}`,
		expectedStatus: http.StatusBadRequest,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{lastFlavor: tt.storeFlavor, errToReturn: tt.storeErr}
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(http.MethodPatch, tt.url, tt.body, adminToken)
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)
			if tt.assertFlavor {
				flavor := &database.Flavor{}
				require.NoError(t, json.Unmarshal([]byte(tt.body), flavor))
				storedFlavor, err := store.GetFlavor(t.Context(), flavor.Name)
				require.NoError(t, err)
				assert.Equal(t, flavor, storedFlavor)
			}
		})
	}
}

func TestDeleteFlavor(t *testing.T) {
	tests := []struct {
		name           string
		storeFlavor    *database.Flavor
		storeErr       error
		url            string
		expectedStatus int
		flavorToAssert string
	}{{
		name: "shouldSucceed",
		storeFlavor: &database.Flavor{
			Platform:        "github",
			Name:            "runner-small",
			Labels:          []string{"x64"},
			Priority:        10,
			IsDisabled:      false,
			MinimumPressure: 5,
		},
		url:            "/api/v1/flavors/runner-small",
		expectedStatus: http.StatusOK,
		flavorToAssert: "runner-small",
	}, {
		name:           "shouldFailWhenFlavorMissing",
		storeErr:       database.ErrNotExist,
		url:            "/api/v1/flavors/not-exist",
		expectedStatus: http.StatusNotFound,
	}, {
		name: "shouldFailWhenNameIsAllFlavors",
		storeFlavor: &database.Flavor{
			Platform:        "github",
			Name:            "runner-small",
			Labels:          []string{"x64"},
			Priority:        10,
			IsDisabled:      false,
			MinimumPressure: 5,
		},
		url:            "/api/v1/flavors/_",
		expectedStatus: http.StatusBadRequest,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{lastFlavor: tt.storeFlavor, errToReturn: tt.storeErr}
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(http.MethodDelete, tt.url, "", adminToken)
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)
			if tt.flavorToAssert != "" {
				// The FakeStore's GetFlavor return nil if no flavor.
				flavor, err := store.GetFlavor(t.Context(), tt.flavorToAssert)
				assert.NoError(t, err)
				assert.Nil(t, flavor)
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
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(tt.method, tt.url, "", adminToken)
			w := httptest.NewRecorder()
			server.ServeHTTP(w, req)

			var resp map[string]int
			json.NewDecoder(w.Body).Decode(&resp)

			assert.Equal(t, tt.expectedStatus, w.Code)
			assert.Equal(t, tt.expectedPressures, resp)
		})
	}
}

func TestGetFlavorPressureStreamHeartbeat(t *testing.T) {
	/*
		arrange: Setup the server with timer control to simulate heartbeat intervals.
		act: Wait for heartbeats in the pressure stream.
		assert: verify that heartbeats are received at expected intervals.
	*/
	ch := make(chan time.Time)
	pressures := atomic.Value{}
	pressures.Store(map[string]int{"runner-small": 1, "runner-medium": 1, "runner-large": 1})
	store := &fakeStore{pressures: pressures, pressureChange: make(chan struct{}, 10)}
	adminToken := "planner_v0_valid_admin_token________________________________"
	server := NewServer(store, store, NewMetrics(store), adminToken, ch)

	ts := httptest.NewUnstartedServer(server)
	ts.StartTLS()
	defer ts.Close()

	req, err := http.NewRequest(http.MethodGet, ts.URL+"/api/v1/flavors/runner-small/pressure?stream=true", nil)
	assert.NoError(t, err)
	req.Header.Set("Authorization", "Bearer "+adminToken)
	resp, err := ts.Client().Do(req)
	assert.NoError(t, err)
	defer resp.Body.Close()

	var res map[string]int
	json.NewDecoder(resp.Body).Decode(&res)
	assert.Equal(t, http.StatusOK, resp.StatusCode)
	assert.Equal(t, map[string]int{"runner-small": 1}, res)

	for i := 0; i < 10; i++ {
		ch <- time.Now()
		json.NewDecoder(resp.Body).Decode(&res)
		assert.Equal(t, http.StatusOK, resp.StatusCode)
		assert.Equal(t, map[string]int{"runner-small": 1}, res)
	}
}

func TestGetFlavorPressureStream(t *testing.T) {
	/*
		arrange: Setup the server.
		act: send streaming requests and update pressures in the store.
		assert: verify the received pressures match expected values, and the HTTP status codes are as expected.
	*/
	tests := []struct {
		name                    string
		http2Enabled            bool
		pressuresStream         []map[string]int
		method                  string
		url                     string
		expectedStatus          []int
		expectedPressuresStream []map[string]int
	}{{
		name:         "shouldSucceedForSingleFlavorWithHTTP2",
		http2Enabled: true,
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
		name:                    "shouldSucceedForAllFlavorsWithHTTP2",
		http2Enabled:            true,
		pressuresStream:         []map[string]int{{"runner-small": 1, "runner-large": 2}, {"runner-small": 3, "runner-large": 4}, {"runner-small": 5, "runner-large": 6}},
		method:                  http.MethodGet,
		url:                     "/api/v1/flavors/_/pressure?stream=true",
		expectedStatus:          []int{http.StatusOK, http.StatusOK, http.StatusOK},
		expectedPressuresStream: []map[string]int{{"runner-small": 1, "runner-large": 2}, {"runner-small": 3, "runner-large": 4}, {"runner-small": 5, "runner-large": 6}},
	}, {
		name:                    "shouldFailWhenFlavorNotExistWithHTTP2",
		http2Enabled:            true,
		pressuresStream:         []map[string]int{{"runner-medium": 2, "runner-large": 1}},
		method:                  http.MethodGet,
		url:                     "/api/v1/flavors/runner-small/pressure?stream=true",
		expectedStatus:          []int{http.StatusNotFound},
		expectedPressuresStream: []map[string]int{nil},
	}, {
		name:         "shouldSucceedForSingleFlavor",
		http2Enabled: false,
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
		http2Enabled:            false,
		pressuresStream:         []map[string]int{{"runner-small": 1, "runner-large": 2}, {"runner-small": 3, "runner-large": 4}, {"runner-small": 5, "runner-large": 6}},
		method:                  http.MethodGet,
		url:                     "/api/v1/flavors/_/pressure?stream=true",
		expectedStatus:          []int{http.StatusOK, http.StatusOK, http.StatusOK},
		expectedPressuresStream: []map[string]int{{"runner-small": 1, "runner-large": 2}, {"runner-small": 3, "runner-large": 4}, {"runner-small": 5, "runner-large": 6}},
	}, {
		name:                    "shouldFailWhenFlavorNotExist",
		http2Enabled:            false,
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
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			ts := httptest.NewUnstartedServer(server)
			ts.EnableHTTP2 = tt.http2Enabled
			ts.StartTLS()
			defer ts.Close()

			req, err := http.NewRequest(http.MethodGet, ts.URL+tt.url, nil)
			assert.NoError(t, err)
			req.Header.Set("Authorization", "Bearer "+adminToken)
			resp, err := ts.Client().Do(req)
			assert.NoError(t, err)
			defer resp.Body.Close()

			var res map[string]int
			for i := range len(tt.pressuresStream) {
				store.pressures.Store(tt.pressuresStream[i])
				store.pressureChange <- struct{}{}

				json.NewDecoder(resp.Body).Decode(&res)
				assert.Equal(t, tt.expectedStatus[i], resp.StatusCode)
				assert.Equal(t, tt.expectedPressuresStream[i], res)
			}
		})
	}
}

func TestHealth(t *testing.T) {
	store := &fakeStore{}
	adminToken := "planner_v0_valid_admin_token________________________________"
	server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

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

func TestAuthTokenEndpoints(t *testing.T) {
	admin := "planner_v0_thisIsAValidAdminToken___________1234"
	t.Run("create token success", func(t *testing.T) {
		token := sha256.Sum256([]byte(admin))
		store := &fakeStore{nameToToken: map[string][32]byte{"github-runner": token}}
		server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))

		req := newRequest(http.MethodPost, "/api/v1/auth/token/github-runner", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)

		assert.Equal(t, http.StatusCreated, w.Code)
		var resp map[string]string
		json.NewDecoder(w.Body).Decode(&resp)
		assert.Equal(t, "github-runner", resp["name"])
		expected := base64.RawURLEncoding.EncodeToString(token[:])
		assert.Equal(t, expected, resp["token"])
	})

	t.Run("create token conflict", func(t *testing.T) {
		store := &fakeStore{createTokErr: database.ErrExist}
		server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
		req := newRequest(http.MethodPost, "/api/v1/auth/token/existing", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusConflict, w.Code)
	})

	t.Run("create token unauthorized", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
		req := newRequest(http.MethodPost, "/api/v1/auth/token/name", "", "invalid-token")
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusUnauthorized, w.Code)
	})

	t.Run("delete token success", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
		req := newRequest(http.MethodDelete, "/api/v1/auth/token/name", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusNoContent, w.Code)
	})

	t.Run("delete token unauthorized", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
		req := newRequest(http.MethodDelete, "/api/v1/auth/token/name", "", "invalid-token")
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusUnauthorized, w.Code)
	})
}

func TestCreateFlavor_Unauthorized(t *testing.T) {
	/*
		arrange: empty store, server with admin token, request uses invalid token
		act: POST /api/v1/flavors/unauth
		assert: returns 401 Unauthorized
	*/
	store := &fakeStore{}
	admin := "planner_v0_valid_admin_token________________________________"
	server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
	body := `{"platform":"github","labels":["x64"],"priority":1}`
	req := newRequest(http.MethodPost, "/api/v1/flavors/unauth", body, "invalid-token")
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusUnauthorized, w.Code)
}

func TestGetFlavorPressure_Unauthorized(t *testing.T) {
	/*
		arrange: store with preset pressures, server with admin token, request uses invalid token
		act: GET /api/v1/flavors/_/pressure
		assert: returns 401 Unauthorized
	*/
	pressures := atomic.Value{}
	pressures.Store(map[string]int{"runner-small": 1})
	store := &fakeStore{pressures: pressures}
	admin := "planner_v0_valid_admin_token________________________________"
	server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
	req := newRequest(http.MethodGet, "/api/v1/flavors/_/pressure", "", "invalid-token")
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusUnauthorized, w.Code)
}
