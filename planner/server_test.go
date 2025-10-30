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
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/prometheus/client_golang/prometheus"
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
	return map[string]int{"test": 1}, nil
}

func (f *fakeStore) VerifyAuthToken(ctx context.Context, token [32]byte) (string, error) {
	if f.tokenIsValid {
		return "validTokenName", nil
	}
	return "", database.ErrNotExist
}

func (f *fakeStore) ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error) {
	return []database.Flavor{}, nil
}

func newMetrics() *Metrics {
	reg := prometheus.NewRegistry()
	return NewMetrics(reg)
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
	// Given a fake store that succeeds and valid auth token
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, newMetrics())
	token := makeToken()

	body := `{"platform":"github","labels":["x64"],"priority":2}`
	req := newRequest(http.MethodPost, "/api/v1/flavors/runner-small", body, token)
	w := httptest.NewRecorder()

	// When creating a flavor
	server.ServeHTTP(w, req)

	// Then it should store the flavor and return 201
	if w.Code != http.StatusCreated {
		t.Errorf("expected status 201, got %d", w.Code)
	}
	if store.lastFlavor.Name != "runner-small" {
		t.Errorf("expected flavor name 'runner-small', got %q", store.lastFlavor.Name)
	}
	if store.lastFlavor.Platform != "github" {
		t.Errorf("expected platform 'github', got %q", store.lastFlavor.Platform)
	}
}

func TestCreateFlavor_shouldFailWhenAlreadyExists(t *testing.T) {
	// Given a store returning database.ErrExist
	store := &fakeStore{errToReturn: database.ErrExist, tokenIsValid: true}
	server := NewServer(store, newMetrics())
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/existing-flavor", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	// When creating an existing flavor
	server.ServeHTTP(w, req)

	// Then it should respond with 409 Conflict
	if w.Code != http.StatusConflict {
		t.Errorf("expected 409 Conflict, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailOnInvalidJSON(t *testing.T) {
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, newMetrics())
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/test", `{invalid-json}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid JSON, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailWhenNameMissing(t *testing.T) {
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, newMetrics())
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("expected 404 missing name, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailUnauthorizedWhenTokenInvalid(t *testing.T) {
	store := &fakeStore{tokenIsValid: false}
	server := NewServer(store, newMetrics())
	token := makeToken()

	req := newRequest(http.MethodPost, "/api/v1/flavors/test", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 Unauthorized, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailForNonPostMethod(t *testing.T) {
	store := &fakeStore{tokenIsValid: true}
	server := NewServer(store, newMetrics())
	token := makeToken()

	req := newRequest(http.MethodGet, "/api/v1/flavors/test", `{"platform":"github"}`, token)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405 for GET, got %d", w.Code)
	}
}
