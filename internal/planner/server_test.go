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
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/stretchr/testify/assert"
)

type fakeStore struct {
	pressures   map[string]int
	lastFlavor  *database.Flavor
	errToReturn error

	// Auth token controls
	nextToken     [32]byte
	createTokErr  error
	deleteTokErr  error
}

func (f *fakeStore) AddFlavor(ctx context.Context, flavor *database.Flavor) error {
	f.lastFlavor = flavor
	return f.errToReturn
}

func (f *fakeStore) GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error) {
	if len(flavors) == 0 {
		return f.pressures, nil
	}
	res := make(map[string]int)
	for _, flavor := range flavors {
		if pressure, ok := f.pressures[flavor]; ok {
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

// AuthStore methods
func (f *fakeStore) CreateAuthToken(ctx context.Context, name string) ([32]byte, error) {
	if f.createTokErr != nil {
		return [32]byte{}, f.createTokErr
	}
	return f.nextToken, nil
}

func (f *fakeStore) DeleteAuthToken(ctx context.Context, name string) error {
	return f.deleteTokErr
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
			server := NewServer(store, store, NewMetrics(store), "planner_v0_valid_admin_token________________________________")
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
			store := &fakeStore{pressures: tt.pressures}
			server := NewServer(store, store, NewMetrics(store), "planner_v0_valid_admin_token________________________________")
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

func TestHealth(t *testing.T) {
	store := &fakeStore{}
	server := NewServer(store, store, NewMetrics(store), "planner_v0_valid_admin_token________________________________")

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
		store := &fakeStore{}
		for i := 0; i < 32; i++ {
			store.nextToken[i] = byte(255 - i)
		}
		server := NewServer(store, store, NewMetrics(store), admin)

		req := newRequest(http.MethodPost, "/api/v1/auth/token/github-runner/0", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)

		assert.Equal(t, http.StatusCreated, w.Code)
		var resp map[string]string
		json.NewDecoder(w.Body).Decode(&resp)
		assert.Equal(t, "github-runner/0", resp["name"])
		expected := base64.RawURLEncoding.EncodeToString(store.nextToken[:])
		assert.Equal(t, expected, resp["token"])
	})

	t.Run("create token conflict", func(t *testing.T) {
		store := &fakeStore{createTokErr: database.ErrExist}
		server := NewServer(store, store, NewMetrics(store), admin)
		req := newRequest(http.MethodPost, "/api/v1/auth/token/existing", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusConflict, w.Code)
	})

	t.Run("create token unauthorized", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin)
		req := newRequest(http.MethodPost, "/api/v1/auth/token/name", "", "")
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusUnauthorized, w.Code)
	})

	t.Run("delete token success", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin)
		req := newRequest(http.MethodDelete, "/api/v1/auth/token/name", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusNoContent, w.Code)
	})

	t.Run("delete token unauthorized", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin)
		req := newRequest(http.MethodDelete, "/api/v1/auth/token/name", "", "")
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusUnauthorized, w.Code)
	})
}
