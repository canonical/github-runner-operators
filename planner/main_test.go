package main

import (
	"net/http"
	"testing"
	"time"
)

// waitForHTTP keeps trying a POST request until the server responds
// with any HTTP status (including 4xx/5xx), or until timeout elapses.
func waitForHTTP(t *testing.T, url string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		resp, err := http.Post(url, "application/json", nil)
		if err == nil {
			resp.Body.Close()
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	t.Fatalf("server did not start responding at %s within %s", url, timeout)
}

// Test that main() starts the HTTP server and it listens on the configured port.
// Assumes POSTGRESQL_DB_CONNECT_STRING and POSTGRESQL_DB_PORT are already set in the environment.
func TestMain_StartsAndListens(t *testing.T) {
	go main()

	// Any HTTP response (including 4xx/5xx) indicates the server is alive and responding
	waitForHTTP(t, "http://localhost:8080/api/v1/flavors/", 10*time.Second)
}
