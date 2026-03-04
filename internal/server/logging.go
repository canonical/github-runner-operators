/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package server

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"time"
)

// LogRequest logs an HTTP request in Apache-style format.
func LogRequest(ctx context.Context, logger *slog.Logger, r *http.Request, receiveTime time.Time, status, bytesWritten int) {
	logger.InfoContext(ctx, fmt.Sprintf(
		"%s - - [%s] \"%s %s %s\" %d %d \"%s\"",
		r.RemoteAddr,
		receiveTime.Format("02/Jan/2006:15:04:05 -0700"),
		r.Method, r.URL.Path, r.Proto,
		status, bytesWritten,
		r.UserAgent()))
}

// LoggingHandler returns middleware that logs every request in Apache-style format.
// It wraps the ResponseWriter to capture the status code and bytes written.
func LoggingHandler(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receiveTime := time.Now()
		rw := &responseWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rw, r)
		LogRequest(r.Context(), logger, r, receiveTime, rw.status, rw.bytes)
	})
}

// responseWriter wraps http.ResponseWriter to capture status code and bytes written.
type responseWriter struct {
	http.ResponseWriter
	status      int
	bytes       int
	wroteHeader bool
}

func (rw *responseWriter) WriteHeader(code int) {
	if !rw.wroteHeader {
		rw.status = code
		rw.wroteHeader = true
	}
	rw.ResponseWriter.WriteHeader(code)
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	n, err := rw.ResponseWriter.Write(b)
	rw.bytes += n
	return n, err
}

func (rw *responseWriter) Flush() {
	if f, ok := rw.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}
