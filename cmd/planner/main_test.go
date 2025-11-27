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
	"encoding/json"
	"math/rand"
	"net/http"
	"os"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
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

	// Test create flavor
	resp := createFlavor(t, port, flavor, platform, labels, priority, pressure)
	if resp != http.StatusCreated {
		t.Fatalf("unexpected status creating flavor: %d", resp)
	}

	// Test get flavor pressure
	pressures := getFlavorPressure(t, port, flavor)
	assertFlavorPressureEquals(t, pressures, flavor, pressure)

	// Test consume webhook and reflect pressure
	rabbitURI := os.Getenv("RABBITMQ_CONNECT_STRING")
	jobID := rand.Intn(1_000_000)
	payload := map[string]any{
		"action": "queued",
		"workflow_job": map[string]any{
			"id":         jobID,
			"labels":     labels,
			"status":     "queued",
			"created_at": time.Now().UTC().Format(time.RFC3339),
		},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal webhook: %v", err)
	}

	publishWebhookMessage(t, rabbitURI, "webhook-queue", body)
	time.Sleep(1 * time.Second)

	// Poll pressure endpoint until assignment reflected
	deadline := time.Now().Add(45 * time.Second)
	for time.Now().Before(deadline) {
		pressures := getFlavorPressure(t, port, flavor)
		if p, ok := pressures[flavor]; ok && p > pressure {
			return
		}
		time.Sleep(500 * time.Millisecond)
	}
	t.Fatalf("pressure did not reflect consumed job for flavor %s within timeout", flavor)
}

// publishWebhookMessage declares the queue and publishes a message for the consumer.
func publishWebhookMessage(t *testing.T, uri, queue string, body []byte) {
	t.Helper()
	conn, err := amqp.Dial(uri)
	if err != nil {
		t.Fatalf("connect rabbitmq: %v", err)
	}
	defer conn.Close()
	ch, err := conn.Channel()
	if err != nil {
		t.Fatalf("open channel: %v", err)
	}
	defer ch.Close()
	if _, err = ch.QueueDeclare(queue, true, false, false, false, nil); err != nil {
		t.Fatalf("declare queue: %v", err)
	}
	_ = ch.Confirm(false)
	if err = ch.Publish("", queue, false, false, amqp.Publishing{ContentType: "application/json", Body: body}); err != nil {
		t.Fatalf("publish message: %v", err)
	}
}

// createFlavor sends a create flavor request to the server
func createFlavor(t *testing.T, port, flavor, platform string, labels []string, priority, pressure int) int {
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

	return resp.StatusCode
}

// getFlavorPressure sends a get flavor pressure request to the server
func getFlavorPressure(t *testing.T, port, flavor string) map[string]int {
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

	return pressures
}

// assertFlavorPressureEquals checks that the pressures map contains the expected pressure for the given flavor
func assertFlavorPressureEquals(t *testing.T, pressures map[string]int, flavor string, expected int) {
	t.Helper()
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

// randString generates a random string of the given length.
func randString(n int) string {
	charset := []rune("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
	b := make([]rune, n)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}
