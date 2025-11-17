/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Integration tests for the Planner API service.
 */

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"math/rand"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
)

func TestMain_CreateFlavor(t *testing.T) {
	/*
		arrange: server is listening on the configured port and prepare request payload
		act: send create flavor request
		assert: expected status code to be either Created (first time) or Conflict (already exists)
	*/
	go main()
	waitForHTTP(t, "http://localhost:8080/api/v1/flavors/", 10*time.Second)

	platform := "github"
	labels := []string{"self-hosted", "amd64"}
	priority := 42
	flavor := randString(10)

	body := map[string]any{
		"platform": platform,
		"labels":   labels,
		"priority": priority,
	}
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	resp, err := http.Post("http://localhost:8080/api/v1/flavors/"+flavor, "application/json", bytes.NewReader(b))
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("unexpected status: %d", resp.StatusCode)
	}

	checkAndCleanupDatabaseFlavor(t, flavor, platform, labels, priority)
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

// checkAndCleanupDatabaseFlavor verifies that the given flavor exists in the database
// with the expected fields, and then deletes it.
func checkAndCleanupDatabaseFlavor(t *testing.T, flavor, platform string, labels []string, priority int) {
	uri := os.Getenv("POSTGRESQL_DB_CONNECT_STRING")
	ctx := context.Background()

	// Apply migrations and connect
	if err := database.Migrate(ctx, uri); err != nil {
		t.Fatalf("migrate failed: %v", err)
	}
	db, err := database.New(ctx, uri)
	if err != nil {
		t.Fatalf("db connect failed: %v", err)
	}

	// Verify flavor exists in DB with expected fields
	flavors, err := db.ListFlavors(ctx, platform)
	if err != nil {
		t.Fatalf("list flavors: %v", err)
	}
	found := false
	for _, f := range flavors {
		if f.Name == flavor {
			found = true
			if f.Priority != priority {
				t.Fatalf("unexpected priority: %d", f.Priority)
			}
			// labels are stored as []string; order should be preserved as sent
			if len(f.Labels) != len(labels) || f.Labels[0] != labels[0] || f.Labels[1] != labels[1] {
				t.Fatalf("unexpected labels: %#v", f.Labels)
			}
			break
		}
	}
	if !found {
		t.Fatalf("flavor %q not found in db", flavor)
	}

	// Cleanup
	_ = db.DeleteFlavor(ctx, platform, flavor)
}

// randString generates a random string of the given length.
func randString(n int) string {
	charset := []rune("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
	b := make([]rune, n)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}
