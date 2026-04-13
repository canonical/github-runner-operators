/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Tests verifying that 5xx responses are logged at ERROR level with error details,
 * and that sensitive request data (e.g. auth tokens) is never included in log output.
 */

package planner

import (
	"bytes"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// withTestLogger replaces the package-level logger for the duration of f and restores it afterwards.
func withTestLogger(t *testing.T, buf *bytes.Buffer, f func()) {
	t.Helper()
	orig := logger
	t.Cleanup(func() { logger = orig })
	logger = slog.New(slog.NewTextHandler(buf, &slog.HandlerOptions{Level: slog.LevelDebug}))
	f()
}

func TestServer5xxLogsAtErrorLevel(t *testing.T) {
	// arrange: inject a DB error so every handler that touches the store returns 500
	dbErr := errors.New("connection refused")
	adminToken := "planner_v0_valid_admin_token________________________________"

	cases := []struct {
		name   string
		store  *fakeStore
		method string
		url    string
		body   string
	}{
		{
			name:   "createFlavor",
			store:  &fakeStore{errToReturn: dbErr},
			method: http.MethodPost,
			url:    "/api/v1/flavors/runner-small",
			body:   `{"platform":"github","labels":["x64"]}`,
		},
		{
			name:   "listFlavors",
			store:  &fakeStore{errToReturn: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/flavors",
			body:   "",
		},
		{
			name:   "getFlavor",
			store:  &fakeStore{errToReturn: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/flavors/runner-small",
			body:   "",
		},
		{
			name:   "updateFlavor",
			store:  &fakeStore{errToReturn: dbErr},
			method: http.MethodPatch,
			url:    "/api/v1/flavors/runner-small",
			body:   `{"is_disabled":true}`,
		},
		{
			name:   "deleteFlavor",
			store:  &fakeStore{errToReturn: dbErr},
			method: http.MethodDelete,
			url:    "/api/v1/flavors/runner-small",
			body:   "",
		},
		{
			name:   "listJobs",
			store:  &fakeStore{listJobsErr: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/jobs/github",
			body:   "",
		},
		{
			name:   "getJob",
			store:  &fakeStore{listJobsErr: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/jobs/github/42",
			body:   "",
		},
		{
			name:   "createAuthToken",
			store:  &fakeStore{createTokErr: dbErr},
			method: http.MethodPost,
			url:    "/api/v1/auth/token/my-token",
			body:   "",
		},
		{
			name:   "listAuthTokens",
			store:  &fakeStore{listTokErr: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/auth/token",
			body:   "",
		},
		{
			name:   "deleteAuthToken",
			store:  &fakeStore{deleteTokErr: dbErr},
			method: http.MethodDelete,
			url:    "/api/v1/auth/token/my-token",
			body:   "",
		},
		{
			name:   "updateJob",
			store:  &fakeStore{listJobsErr: dbErr},
			method: http.MethodPatch,
			url:    "/api/v1/jobs/github/42",
			body:   `{"started_at":"2026-01-01T00:00:00Z"}`,
		},
		{
			name:   "getFlavorPressureGetError",
			store:  &fakeStore{getPressuresErr: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/flavors/runner-small/pressure",
			body:   "",
		},
		{
			name:   "getFlavorPressureSubscribeError",
			store:  &fakeStore{subscribeToPressureErr: dbErr},
			method: http.MethodGet,
			url:    "/api/v1/flavors/runner-small/pressure?stream=true",
			body:   "",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var buf bytes.Buffer
			withTestLogger(t, &buf, func() {
				srv := NewServer(tc.store, tc.store, NewMetrics(tc.store), adminToken, nil)
				req := newRequest(tc.method, tc.url, tc.body, adminToken)
				w := httptest.NewRecorder()
				srv.ServeHTTP(w, req)

				require.Equal(t, http.StatusInternalServerError, w.Code)
				output := buf.String()
				assert.Contains(t, output, "ERROR", "expected ERROR log level for 5xx response")
				assert.Contains(t, output, dbErr.Error(), "expected error detail in log")
			})
		})
	}
}

func TestServer5xxDoesNotLeakAuthToken(t *testing.T) {
	// arrange: inject a DB error and use a recognisable admin token
	dbErr := errors.New("db failure")
	store := &fakeStore{errToReturn: dbErr}
	adminToken := "super-secret-admin-token-that-must-not-appear-in-logs"

	var buf bytes.Buffer
	withTestLogger(t, &buf, func() {
		srv := NewServer(store, store, NewMetrics(store), adminToken, nil)
		req := newRequest(http.MethodGet, "/api/v1/flavors", "", adminToken)
		w := httptest.NewRecorder()
		srv.ServeHTTP(w, req)

		require.Equal(t, http.StatusInternalServerError, w.Code)
		assert.NotContains(t, buf.String(), adminToken, "auth token must not appear in log output")
	})
}

func TestServer2xxLogsAtInfoNotError(t *testing.T) {
	// arrange: a healthy store so requests succeed
	store := &fakeStore{}
	adminToken := "planner_v0_valid_admin_token________________________________"

	var buf bytes.Buffer
	withTestLogger(t, &buf, func() {
		srv := NewServer(store, store, NewMetrics(store), adminToken, nil)
		req := newRequest(http.MethodGet, "/health", "", "")
		w := httptest.NewRecorder()
		srv.ServeHTTP(w, req)

		require.Equal(t, http.StatusOK, w.Code)
		assert.NotContains(t, buf.String(), "ERROR", "healthy responses must not produce ERROR log entries")
	})
}
