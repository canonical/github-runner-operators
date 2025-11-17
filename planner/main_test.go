package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"testing"
	"time"
)

func TestMain_StartsAndListens(t *testing.T) {
	/*
		arrange: assumes POSTGRESQL_DB_CONNECT_STRING and POSTGRESQL_DB_PORT are already set in the environment
		act: starts the HTTP server via main()
		assert: server is listening on the configured port
	*/
	go main()

	waitForHTTP(t, "http://localhost:8080/api/v1/flavors/", 10*time.Second)
}

func TestMain_CreateFlavor(t *testing.T) {
	/*
		arrange: server is listening on the configured port and prepare request payload
		act: send create flavor request
		assert: expected status code to be either Created (first time) or Conflict (already exists)
	*/
	body := map[string]any{
		"platform": "github",
		"labels":   []string{"self-hosted", "amd64"},
		"priority": 42,
	}
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	resp, err := http.Post("http://localhost:8080/api/v1/flavors/it-flavor", "application/json", bytes.NewReader(b))
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()

	if (resp.StatusCode != http.StatusCreated) && (resp.StatusCode != http.StatusConflict) {
		t.Fatalf("unexpected status: %d", resp.StatusCode)
	}
}

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
