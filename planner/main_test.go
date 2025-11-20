//go:build integration

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

func TestMain_FlavorPressure(t *testing.T) {
	/*
		arrange: server is listening on the configured port and prepare request payload
		act: send create flavor request and get flavor pressure request
		assert: 201 Created and 200 OK with expected pressure value
	*/
	go main()
	port := os.Getenv("APP_PORT")
	waitForHTTP(t, "http://localhost:"+port+"/api/v1/flavors/", 10*time.Second)

	platform := "github"
	labels := []string{"self-hosted", "amd64"}
	priority := 42
	flavor := randString(10)
	pressure := 7

	testCreateFlavor(t, port, flavor, platform, labels, priority, pressure)
	testGetFlavorPressure(t, port, flavor, pressure)
}

// testCreateFlavor sends a create flavor request to the server
// and verifies the response status is 201 Created.
func testCreateFlavor(t *testing.T, port, flavor, platform string, labels []string, priority, pressure int) {
	t.Helper()

	body := map[string]any{
		"platform":         platform,
		"labels":           labels,
		"priority":         priority,
		"minimum_pressure": pressure,
	}

	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	url := "http://localhost:" + port + "/api/v1/flavors/" + flavor

	resp, err := http.Post(url, "application/json", bytes.NewReader(b))
	if err != nil {
		t.Fatalf("create flavor request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("unexpected status creating flavor: %d", resp.StatusCode)
	}
}

// testGetFlavorPressure sends a get flavor pressure request to the server
// and verifies the response contains the expected pressure value.
func testGetFlavorPressure(t *testing.T, port, flavor string, expected int) {
	t.Helper()

	url := "http://localhost:" + port + "/api/v1/flavors/" + flavor + "/pressure"

	resp, err := http.Get(url)
	if err != nil {
		t.Fatalf("get flavor pressure request: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("unexpected status getting pressure: %d", resp.StatusCode)
	}

	var pressures map[string]int
	if err := json.NewDecoder(resp.Body).Decode(&pressures); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	value, exists := pressures[flavor]
	if !exists {
		t.Fatalf("expected flavor %q in response, got %+v", flavor, pressures)
	}

	if value != expected {
		t.Fatalf("expected pressure %d for flavor %q, got %d", expected, flavor, value)
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

// checkAndCleanupDatabaseFlavor verifies that the given flavor exists in the database
// with the expected fields, and then deletes it.
func checkAndCleanupDatabaseFlavor(t *testing.T, flavor, platform string, labels []string, priority int) {
	ctx := context.Background()
	db := applyMigrationAndConnectDB(t, ctx)

	verifyFlavorExistsInDB(t, ctx, db, flavor, platform, labels, priority)

	// Cleanup
	_ = db.DeleteFlavor(ctx, platform, flavor)
}

// applyMigrationAndConnectDB applies database migrations and connects to the database.
func applyMigrationAndConnectDB(t *testing.T, ctx context.Context) *database.Database {
	uri := os.Getenv("POSTGRESQL_DB_CONNECT_STRING")

	if err := database.Migrate(ctx, uri); err != nil {
		t.Fatalf("migrate failed: %v", err)
	}
	db, err := database.New(ctx, uri)
	if err != nil {
		t.Fatalf("db connect failed: %v", err)
	}
	return db
}

// verifyFlavorExistsInDB checks that the specified flavor exists in the database
// with the expected labels and priority.
func verifyFlavorExistsInDB(t *testing.T, ctx context.Context, db *database.Database, flavor, platform string, labels []string, priority int) {
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
			if len(f.Labels) != len(labels) || f.Labels[0] != labels[0] || f.Labels[1] != labels[1] {
				t.Fatalf("unexpected labels: %#v", f.Labels)
			}
			break
		}
	}
	if !found {
		t.Fatalf("flavor %q not found in db", flavor)
	}
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
