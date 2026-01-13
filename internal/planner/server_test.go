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
	createTokErr error
	deleteTokErr error

	nameToToken map[string][32]byte
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

func newRequest(method, url, body string, token string) *http.Request {
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
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken)

			req := newRequest(tt.method, tt.url, tt.body, adminToken)
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
			adminToken := "planner_v0_valid_admin_token________________________________"
			server := NewServer(store, store, NewMetrics(store), adminToken)

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
		token := sha256.Sum256([]byte(admin))
		store := &fakeStore{nameToToken: map[string][32]byte{"github-runner": token}}
		server := NewServer(store, store, NewMetrics(store), admin)

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
		server := NewServer(store, store, NewMetrics(store), admin)
		req := newRequest(http.MethodPost, "/api/v1/auth/token/existing", "", admin)
		w := httptest.NewRecorder()
		server.ServeHTTP(w, req)
		assert.Equal(t, http.StatusConflict, w.Code)
	})

	t.Run("create token unauthorized", func(t *testing.T) {
		store := &fakeStore{}
		server := NewServer(store, store, NewMetrics(store), admin)
		req := newRequest(http.MethodPost, "/api/v1/auth/token/name", "", "invalid-token")
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
	server := NewServer(store, store, NewMetrics(store), admin)
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
	store := &fakeStore{pressures: map[string]int{"runner-small": 1}}
	admin := "planner_v0_valid_admin_token________________________________"
	server := NewServer(store, store, NewMetrics(store), admin)
	req := newRequest(http.MethodGet, "/api/v1/flavors/_/pressure", "", "invalid-token")
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	assert.Equal(t, http.StatusUnauthorized, w.Code)
}
