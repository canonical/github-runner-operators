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
	"github.com/stretchr/testify/require"
)

func TestMain_FlavorPressure(t *testing.T) {
	/*
		arrange: server is listening on the configured port and prepare request payload
		act: send create flavor request, get flavor pressure request and publish webhook message
		assert: 201 Created and 200 OK with expected pressure value updated after webhook processing
	*/
	rabbitURI := os.Getenv("RABBITMQ_CONNECT_STRING")
	port := os.Getenv("APP_PORT")
	declareQueue(t, rabbitURI, "webhook-queue")

	go main()
	waitForHTTP(t, "http://localhost:"+port+"/api/v1/flavors/", 10*time.Second)

	platform := "github"
	labels := []string{"self-hosted", "s390x", "medium"}
	priority := 100
	flavor := randString(10)
	pressure := 0

	// Test create flavor
	resp := createFlavor(t, port, flavor, platform, labels, priority)
	if resp != http.StatusCreated {
		t.Fatalf("unexpected status creating flavor: %d", resp)
	}

	// Test get flavor pressure
	pressures := getFlavorPressure(t, port, flavor)
	assertFlavorPressureEquals(t, pressures, flavor, pressure)

	// Test consume webhook and reflect pressure
	body := constructWebhookPayload(t, labels)
	publishAndWaitAck(t, rabbitURI, "webhook-queue", body)

	require.Eventually(t, func() bool {
		press := getFlavorPressure(t, port, flavor)
		return press[flavor] > pressure
	}, 20*time.Minute, 500*time.Millisecond)
}

// constructWebhookPayload creates a webhook payload with the given labels.
func constructWebhookPayload(t *testing.T, labels []string) []byte {
	jobID := rand.Intn(1000)
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
		require.NoError(t, err, "marshal webhook payload")
	}
	return body
}

// declareQueue declares a RabbitMQ queue for testing purposes.
func declareQueue(t *testing.T, uri, queue string) {
	t.Helper()

	conn, err := amqp.Dial(uri)
	require.NoError(t, err, "connect rabbitmq")
	defer conn.Close()

	ch, err := conn.Channel()
	require.NoError(t, err, "open channel")
	defer ch.Close()

	_, err = ch.QueueDeclare(
		queue,
		true,  // durable
		false, // auto-delete
		false, // exclusive
		false, // no-wait
		nil,
	)
	require.NoError(t, err, "declare queue")
}

// publishAndWaitAck publishes a message to the given RabbitMQ queue and waits for an ack.
func publishAndWaitAck(t *testing.T, uri, queue string, body []byte) {
	t.Helper()

	conn, err := amqp.Dial(uri)
	require.NoError(t, err, "connect rabbitmq")
	defer conn.Close()

	ch, err := conn.Channel()
	require.NoError(t, err, "open channel")
	defer ch.Close()

	err = ch.Confirm(false)
	require.NoError(t, err, "enable confirms")

	confirms := ch.NotifyPublish(make(chan amqp.Confirmation, 1))

	err = ch.Publish(
		"", queue, false, false,
		amqp.Publishing{ContentType: "application/json", Body: body},
	)
	require.NoError(t, err, "publish")

	select {
	case c := <-confirms:
		require.True(t, c.Ack, "message not acked")
	case <-time.After(10 * time.Second):
		require.Fail(t, "timeout waiting for ack")
	}
}

// createFlavor sends a create flavor request to the server
func createFlavor(t *testing.T, port, flavor, platform string, labels []string, priority int) int {
	t.Helper()

	body := map[string]any{
		"platform": platform,
		"labels":   labels,
		"priority": priority,
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
