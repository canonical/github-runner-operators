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
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
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

	// Job controls
	jobs           map[string]*database.Job
	listJobsErr    error
	updateStartErr error
	updateComplErr error
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

func (f *fakeStore) ListJobs(ctx context.Context, platform string, option ...database.ListJobOptions) ([]database.Job, error) {
	if f.listJobsErr != nil {
		return nil, f.listJobsErr
	}
	if f.jobs == nil {
		return []database.Job{}, nil
	}
	var results []database.Job
	for key, job := range f.jobs {
		if job.Platform != platform {
			continue
		}
		if len(option) > 0 && option[0].WithId != "" && job.ID != option[0].WithId {
			continue
		}
		results = append(results, *f.jobs[key])
	}
	return results, nil
}

func (f *fakeStore) UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]interface{}) error {
	if f.updateStartErr != nil {
		return f.updateStartErr
	}
	key := platform + ":" + id
	if job, ok := f.jobs[key]; ok {
		job.StartedAt = &startedAt
		return nil
	}
	return database.ErrNotExist
}

func (f *fakeStore) UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]interface{}) error {
	if f.updateComplErr != nil {
		return f.updateComplErr
	}
	key := platform + ":" + id
	if job, ok := f.jobs[key]; ok {
		job.CompletedAt = &completedAt
		return nil
	}
	return database.ErrNotExist
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
	/*
		arrange: Setup the server.
		act: Make get flavor requests.
		assert: Verify the flavors returned are correct, and/or the HTTP status codes are as expected.
	*/
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
		expectedStatus: http.StatusBadRequest,
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
	/*
		arrange: Setup the server.
		act: Make update flavor requests.
		assert: Verify the flavors are updated, and/or the HTTP status codes are as expected.
	*/
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
	/*
		arrange: Setup the server.
		act: Make delete flavor requests.
		assert: Verify the flavors are deleted, and/or the HTTP status codes are as expected.
	*/
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

func TestEndpoints_Unauthorized(t *testing.T) {
	/*
		arrange: various stores and endpoints
		act: send requests with invalid token
		assert: all return 401 Unauthorized
	*/
	createdAt := time.Date(2025, 1, 1, 10, 0, 0, 0, time.UTC)
	newStartedAt := time.Date(2025, 1, 1, 10, 6, 0, 0, time.UTC)

	tests := []struct {
		name   string
		method string
		url    string
		body   string
	}{{
		name:   "CreateFlavor",
		method: http.MethodPost,
		url:    "/api/v1/flavors/runner-small",
		body:   `{"platform":"github","labels":["x64"],"priority":1}`,
	}, {
		name:   "GetFlavorPressure",
		method: http.MethodGet,
		url:    "/api/v1/flavors/_/pressure",
		body:   "",
	}, {
		name:   "GetJob",
		method: http.MethodGet,
		url:    "/api/v1/jobs/github/job-1",
		body:   "",
	}, {
		name:   "UpdateJob",
		method: http.MethodPatch,
		url:    "/api/v1/jobs/github/job-1",
		body:   fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Setup store with necessary data
			pressures := atomic.Value{}
			pressures.Store(map[string]int{"runner-small": 1})
			store := &fakeStore{
				pressures: pressures,
				jobs: map[string]*database.Job{
					"github:job-1": {
						Platform:  "github",
						ID:        "job-1",
						Labels:    []string{"x64"},
						CreatedAt: createdAt,
					},
				},
			}

			admin := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), admin, time.Tick(30*time.Second))
			req := newRequest(tt.method, tt.url, tt.body, "invalid-token")
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, http.StatusUnauthorized, w.Code)
		})
	}
}

func TestGetJob(t *testing.T) {
	/*
		arrange: setup fake store with jobs, server with admin token
		act: send requests to get specific job and list jobs for platform
		assert: verify responses match expected status codes and job counts
	*/
	createdAt := time.Date(2026, 1, 1, 10, 0, 0, 0, time.UTC)
	startedAt := time.Date(2026, 1, 1, 10, 5, 0, 0, time.UTC)
	completedAt := time.Date(2026, 1, 1, 10, 10, 0, 0, time.UTC)

	tests := []struct {
		name           string
		jobs           map[string]*database.Job
		listJobsErr    error
		method         string
		url            string
		expectedStatus int
		expectedCount  int
	}{{
		name: "shouldSucceedGettingSpecificJob",
		jobs: map[string]*database.Job{
			"github:job-123": {
				Platform:    "github",
				ID:          "job-123",
				Labels:      []string{"x64", "large"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: nil,
				Raw:         map[string]interface{}{"key": "value"},
			},
		},
		method:         http.MethodGet,
		url:            "/api/v1/jobs/github/job-123",
		expectedStatus: http.StatusOK,
		expectedCount:  1,
	}, {
		name: "shouldSucceedListingAllJobsForPlatform",
		jobs: map[string]*database.Job{
			"github:job-1": {
				Platform:    "github",
				ID:          "job-1",
				Labels:      []string{"x64"},
				CreatedAt:   createdAt,
				StartedAt:   &startedAt,
				CompletedAt: nil,
			},
			"github:job-2": {
				Platform:    "github",
				ID:          "job-2",
				Labels:      []string{"arm64"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: &completedAt,
			},
		},
		method:         http.MethodGet,
		url:            "/api/v1/jobs/github",
		expectedStatus: http.StatusOK,
		expectedCount:  2,
	}, {
		name: "shouldFailWhenJobNotFound",
		jobs: map[string]*database.Job{
			"github:job-123": {
				Platform:    "github",
				ID:          "job-123",
				Labels:      []string{"x64", "large"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: nil,
				Raw:         map[string]interface{}{"key": "value"},
			},
		},
		method:         http.MethodGet,
		url:            "/api/v1/jobs/github/nonexistent",
		expectedStatus: http.StatusNotFound,
	}, {
		name:           "shouldFailWhenPlatformMissing",
		method:         http.MethodGet,
		url:            "/api/v1/jobs//job-1",
		expectedStatus: http.StatusMovedPermanently,
	}, {
		name:           "shouldFailOnDatabaseError",
		listJobsErr:    errors.New("database error"),
		method:         http.MethodGet,
		url:            "/api/v1/jobs/github/job-1",
		expectedStatus: http.StatusInternalServerError,
	}, {
		name:           "shouldFailForNonGetMethod",
		method:         http.MethodPost,
		url:            "/api/v1/jobs/github/job-1",
		expectedStatus: http.StatusMethodNotAllowed,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{
				jobs:        tt.jobs,
				listJobsErr: tt.listJobsErr,
			}
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(tt.method, tt.url, "", adminToken)
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)

			if tt.expectedCount > 0 {
				var jobs []database.Job
				err := json.NewDecoder(w.Body).Decode(&jobs)
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedCount, len(jobs))
				assertJobsMatch(t, tt.jobs, jobs)
			}
		})
	}
}

// assertJobsMatch verifies that the returned jobs match the expected jobs from the test data
func assertJobsMatch(t *testing.T, expected map[string]*database.Job, actual []database.Job) {
	t.Helper()
	for _, job := range actual {
		key := job.Platform + ":" + job.ID
		expectedJob, exists := expected[key]
		assert.True(t, exists, "Unexpected job returned: %s", key)
		if exists {
			assert.Equal(t, expectedJob.Platform, job.Platform)
			assert.Equal(t, expectedJob.ID, job.ID)
			assert.Equal(t, expectedJob.Labels, job.Labels)
			assert.Equal(t, expectedJob.CreatedAt, job.CreatedAt)
			assert.Equal(t, expectedJob.StartedAt, job.StartedAt)
			assert.Equal(t, expectedJob.CompletedAt, job.CompletedAt)
			assert.Equal(t, expectedJob.Raw, job.Raw)
		}
	}
}

func TestUpdateJob(t *testing.T) {
	/*
		arrange: setup fake store with jobs, server with admin token
		act: send requests to update job's started_at and completed_at fields
		assert: verify responses match expected status codes and job updates
	*/
	createdAt := time.Date(2025, 1, 1, 10, 0, 0, 0, time.UTC)
	startedAt := time.Date(2025, 1, 1, 10, 5, 0, 0, time.UTC)
	completedAt := time.Date(2025, 1, 1, 10, 10, 0, 0, time.UTC)
	newStartedAt := time.Date(2025, 1, 1, 10, 6, 0, 0, time.UTC)
	newCompletedAt := time.Date(2025, 1, 1, 10, 11, 0, 0, time.UTC)

	tests := []struct {
		name           string
		jobs           map[string]*database.Job
		listJobsErr    error
		updateStartErr error
		updateComplErr error
		method         string
		url            string
		body           string
		expectedStatus int
	}{{
		name: "shouldSucceedUpdatingStartedAt",
		jobs: map[string]*database.Job{
			"github:job-1": {
				Platform:    "github",
				ID:          "job-1",
				Labels:      []string{"x64"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: nil,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-1",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusNoContent,
	}, {
		name: "shouldSucceedUpdatingCompletedAt",
		jobs: map[string]*database.Job{
			"github:job-2": {
				Platform:    "github",
				ID:          "job-2",
				Labels:      []string{"arm64"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: nil,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-2",
		body:           fmt.Sprintf(`{"completed_at":"%s"}`, newCompletedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusNoContent,
	}, {
		name: "shouldSucceedUpdatingBothFields",
		jobs: map[string]*database.Job{
			"github:job-3": {
				Platform:    "github",
				ID:          "job-3",
				Labels:      []string{"x64"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: nil,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-3",
		body:           fmt.Sprintf(`{"started_at":"%s","completed_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano), newCompletedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusNoContent,
	}, {
		name: "shouldFailWhenStartedAtNotNull",
		jobs: map[string]*database.Job{
			"github:job-4": {
				Platform:    "github",
				ID:          "job-4",
				Labels:      []string{"x64"},
				CreatedAt:   createdAt,
				StartedAt:   &startedAt,
				CompletedAt: nil,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-4",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusInternalServerError,
	}, {
		name: "shouldFailWhenCompletedAtNotNull",
		jobs: map[string]*database.Job{
			"github:job-5": {
				Platform:    "github",
				ID:          "job-5",
				Labels:      []string{"x64"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: &completedAt,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-5",
		body:           fmt.Sprintf(`{"completed_at":"%s"}`, newCompletedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusInternalServerError,
	}, {
		name: "shouldSucceedUpdatingStartedAtEvenWhenCompletedAtNotNull",
		jobs: map[string]*database.Job{
			"github:job-6": {
				Platform:    "github",
				ID:          "job-6",
				Labels:      []string{"x64"},
				CreatedAt:   createdAt,
				StartedAt:   nil,
				CompletedAt: &completedAt,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-6",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusNoContent,
	}, {
		name:           "shouldFailWhenJobNotFound",
		jobs:           map[string]*database.Job{},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/nonexistent",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusNotFound,
	}, {
		name: "shouldFailWhenPlatformMissing",
		jobs: map[string]*database.Job{
			"github:job-7": {
				Platform:  "github",
				ID:        "job-7",
				CreatedAt: createdAt,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs//job-7",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusMovedPermanently,
	}, {
		name: "shouldFailWhenIdMissing",
		jobs: map[string]*database.Job{
			"github:job-8": {
				Platform:  "github",
				ID:        "job-8",
				CreatedAt: createdAt,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusNotFound,
	}, {
		name: "shouldFailOnInvalidJSON",
		jobs: map[string]*database.Job{
			"github:job-9": {
				Platform:  "github",
				ID:        "job-9",
				CreatedAt: createdAt,
			},
		},
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-9",
		body:           `{invalid-json}`,
		expectedStatus: http.StatusBadRequest,
	}, {
		name: "shouldFailOnListJobsError",
		jobs: map[string]*database.Job{
			"github:job-10": {
				Platform:  "github",
				ID:        "job-10",
				CreatedAt: createdAt,
			},
		},
		listJobsErr:    errors.New("database error"),
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-10",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusInternalServerError,
	}, {
		name: "shouldFailOnUpdateStartedError",
		jobs: map[string]*database.Job{
			"github:job-11": {
				Platform:  "github",
				ID:        "job-11",
				CreatedAt: createdAt,
			},
		},
		updateStartErr: errors.New("update error"),
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-11",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusInternalServerError,
	}, {
		name: "shouldFailOnUpdateCompletedError",
		jobs: map[string]*database.Job{
			"github:job-12": {
				Platform:  "github",
				ID:        "job-12",
				CreatedAt: createdAt,
			},
		},
		updateComplErr: errors.New("update error"),
		method:         http.MethodPatch,
		url:            "/api/v1/jobs/github/job-12",
		body:           fmt.Sprintf(`{"completed_at":"%s"}`, newCompletedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusInternalServerError,
	}, {
		name: "shouldFailForNonPatchMethod",
		jobs: map[string]*database.Job{
			"github:job-13": {
				Platform:  "github",
				ID:        "job-13",
				CreatedAt: createdAt,
			},
		},
		method:         http.MethodPost,
		url:            "/api/v1/jobs/github/job-13",
		body:           fmt.Sprintf(`{"started_at":"%s"}`, newStartedAt.Format(time.RFC3339Nano)),
		expectedStatus: http.StatusMethodNotAllowed,
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			store := &fakeStore{
				jobs:           tt.jobs,
				listJobsErr:    tt.listJobsErr,
				updateStartErr: tt.updateStartErr,
				updateComplErr: tt.updateComplErr,
			}
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken, time.Tick(30*time.Second))

			req := newRequest(tt.method, tt.url, tt.body, adminToken)
			w := httptest.NewRecorder()

			server.ServeHTTP(w, req)

			assert.Equal(t, tt.expectedStatus, w.Code)

			// Verify job was actually updated if success
			if tt.expectedStatus == http.StatusNoContent && tt.jobs != nil {
				for key, job := range store.jobs {
					if strings.Contains(tt.body, "started_at") {
						assert.Equal(t, &newStartedAt, job.StartedAt, "Job %s started_at was not updated correctly", key)
					}
					if strings.Contains(tt.body, "completed_at") {
						assert.Equal(t, &newCompletedAt, job.CompletedAt, "Job %s completed_at was not updated correctly", key)
					}
				}
			}
		})
	}
}
