/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Test file for planner package.
 */

package planner_test

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/planner"
)

type fakeStore struct {
	lastFlavor  *database.Flavor
	errToReturn error
}

func (f *fakeStore) AddFlavor(ctx context.Context, flavor *database.Flavor) error {
	f.lastFlavor = flavor
	return f.errToReturn
}

func newRequest(method, url, body string) *http.Request {
	req := httptest.NewRequest(method, url, bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	return req
}

func TestCreateFlavor_shouldSucceed(t *testing.T) {
	// Given a fake store that succeeds
	store := &fakeStore{}
	server := planner.NewServer(store)

	body := `{"platform":"github","labels":["x64"],"priority":2}`
	req := newRequest(http.MethodPost, "/api/v1/flavors/runner-small", body)
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
	store := &fakeStore{errToReturn: database.ErrExist}
	server := planner.NewServer(store)

	req := newRequest(http.MethodPost, "/api/v1/flavors/test", `{"platform":"github"}`)
	w := httptest.NewRecorder()

	// When creating an existing flavor
	server.ServeHTTP(w, req)

	// Then it should respond with 409 Conflict
	if w.Code != http.StatusConflict {
		t.Errorf("expected 409 Conflict, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailOnInvalidJSON(t *testing.T) {
	store := &fakeStore{}
	server := planner.NewServer(store)

	req := newRequest(http.MethodPost, "/api/v1/flavors/test", `{invalid-json}`)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid JSON, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailWhenNameMissing(t *testing.T) {
	store := &fakeStore{}
	server := planner.NewServer(store)

	req := newRequest(http.MethodPost, "/api/v1/flavors/", `{"platform":"github"}`)
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 missing name, got %d", w.Code)
	}
}

func TestCreateFlavor_shouldFailForNonPostMethod(t *testing.T) {
	store := &fakeStore{}
	server := planner.NewServer(store)

	req := newRequest(http.MethodGet, "/api/v1/flavors/test", "")
	w := httptest.NewRecorder()

	server.ServeHTTP(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Errorf("expected 405 for GET, got %d", w.Code)
	}
}
