/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package server

import (
	"bytes"
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLogRequest(t *testing.T) {
	// arrange: build a request and a logger that writes to a buffer
	// act: call LogRequest
	// assert: the log output contains the expected format
	var buf bytes.Buffer
	testLogger := slog.New(slog.NewTextHandler(&buf, nil))
	receiveTime := time.Date(2025, 6, 15, 14, 30, 0, 0, time.UTC)
	req, err := http.NewRequest("GET", "/api/v1/flavors", nil)
	require.NoError(t, err)
	req.RemoteAddr = "192.168.1.1:12345"
	req.Header.Set("User-Agent", "test-agent/1.0")

	LogRequest(context.Background(), testLogger, req, receiveTime, http.StatusOK, 42)

	output := buf.String()
	assert.Contains(t, output, "192.168.1.1:12345")
	assert.Contains(t, output, "15/Jun/2025:14:30:00 +0000")
	assert.Contains(t, output, "GET /api/v1/flavors HTTP/1.1")
	assert.Contains(t, output, "200 42")
	assert.Contains(t, output, "test-agent/1.0")
}

func TestLogRequestErrorStatus(t *testing.T) {
	// arrange: build a request that results in an error status
	// act: call LogRequest with a 401 status
	// assert: the log output contains the 401 status
	var buf bytes.Buffer
	testLogger := slog.New(slog.NewTextHandler(&buf, nil))
	receiveTime := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	req, err := http.NewRequest("POST", "/webhook", nil)
	require.NoError(t, err)
	req.RemoteAddr = "10.0.0.1:9999"

	LogRequest(context.Background(), testLogger, req, receiveTime, http.StatusUnauthorized, 0)

	output := buf.String()
	assert.Contains(t, output, "401 0")
	assert.Contains(t, output, "10.0.0.1:9999")
}

func TestLoggingHandler(t *testing.T) {
	// arrange: wrap a handler that writes a known response
	// act: serve a request through LoggingHandler
	// assert: the log output contains captured status and bytes
	var buf bytes.Buffer
	testLogger := slog.New(slog.NewTextHandler(&buf, nil))
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte("hello"))
	})

	req := httptest.NewRequest("POST", "/test", nil)
	req.RemoteAddr = "10.0.0.1:8080"
	rec := httptest.NewRecorder()

	LoggingHandler(testLogger, inner).ServeHTTP(rec, req)

	output := buf.String()
	assert.Contains(t, output, "10.0.0.1:8080")
	assert.Contains(t, output, "POST /test HTTP/1.1")
	assert.Contains(t, output, "201 5")
}

func TestLoggingHandlerDefaultStatus(t *testing.T) {
	// arrange: wrap a handler that writes a body without calling WriteHeader
	// act: serve a request through LoggingHandler
	// assert: the log output shows 200 (implicit)
	var buf bytes.Buffer
	testLogger := slog.New(slog.NewTextHandler(&buf, nil))
	inner := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})

	req := httptest.NewRequest("GET", "/health", nil)
	rec := httptest.NewRecorder()

	LoggingHandler(testLogger, inner).ServeHTTP(rec, req)

	output := buf.String()
	assert.Contains(t, output, "200 2")
}
