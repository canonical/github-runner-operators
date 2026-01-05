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
	"syscall"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// testContext holds test configuration and dependencies.
type testContext struct {
	t         *testing.T
	port      string
	rabbitURI string
	queueName string
}

func newTestContext(t *testing.T) *testContext {
	return &testContext{
		t:         t,
		port:      os.Getenv("APP_PORT"),
		rabbitURI: os.Getenv("RABBITMQ_CONNECT_STRING"),
		queueName: "webhook-queue",
	}
}

func TestMain_FlavorPressure(t *testing.T) {
	/*
		arrange: server is listening on the configured port and prepare request payload
		act: send create flavor request, get flavor pressure request and publish webhook message
		assert: 201 Created and 200 OK with expected pressure value updated after webhook processing
	*/
	ctx := newTestContext(t)
	ctx.declareQueue()

	go main()
	ctx.waitForHTTP("http://localhost:"+ctx.port+"/health", 10*time.Second)

	platform := "github"
	labels := []string{"self-hosted", "s390x", "medium"}
	priority := 100
	flavor := randString(10)
	pressure := 0

	// Test create flavor
	resp := ctx.createFlavor(flavor, platform, labels, priority)
	require.Equal(t, http.StatusCreated, resp, "unexpected status creating flavor")

	// Test get flavor pressure
	pressures := ctx.getFlavorPressure(flavor)
	ctx.assertFlavorPressureEquals(pressures, flavor, pressure)

	// Test consume webhook and reflect pressure
	body := ctx.constructWebhookPayload(labels)
	ctx.publishAndWaitAck(body)

	assert.Eventually(t, func() bool {
		press := ctx.getFlavorPressure(flavor)
		return press[flavor] > pressure
	}, 20*time.Minute, 500*time.Millisecond)

	// Trigger graceful shutdown and verify services stop cleanly
	ctx.shutdownMain()
	ctx.waitForHTTPDown("http://localhost:"+ctx.port+"/health", 30*time.Second)

	// Verify AMQP consumer is stopped by checking queue depth increases after publish
	beforeDepth := ctx.getQueueDepth()
	body2 := ctx.constructWebhookPayload(labels)
	ctx.publishAndWaitAck(body2)

	assert.Eventually(t, func() bool {
		return ctx.getQueueDepth() >= beforeDepth+1
	}, 10*time.Second, 200*time.Millisecond, "expected queue depth to increase after shutdown (consumer stopped)")
}

// constructWebhookPayload creates a webhook payload with the given labels.
func (ctx *testContext) constructWebhookPayload(labels []string) []byte {
	jobID := rand.Intn(1000)
	payload := map[string]any{
		"action": "queued",
		"repository": map[string]any{
			"full_name": "canonical/test",
		},
		"workflow_job": map[string]any{
			"id":         jobID,
			"labels":     labels,
			"status":     "queued",
			"created_at": time.Now().UTC().Format(time.RFC3339),
		},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		require.NoError(ctx.t, err, "marshal webhook payload")
	}
	return body
}

// declareQueue declares a RabbitMQ queue for testing purposes.
func (ctx *testContext) declareQueue() {
	ctx.t.Helper()

	conn, err := amqp.Dial(ctx.rabbitURI)
	require.NoError(ctx.t, err, "connect rabbitmq")
	defer conn.Close()

	ch, err := conn.Channel()
	require.NoError(ctx.t, err, "open channel")
	defer ch.Close()

	_, err = ch.QueueDeclare(
		ctx.queueName,
		true,  // durable
		false, // auto-delete
		false, // exclusive
		false, // no-wait
		nil,
	)
	require.NoError(ctx.t, err, "declare queue")
}

// publishAndWaitAck publishes a message to the given RabbitMQ queue and waits for an ack.
func (ctx *testContext) publishAndWaitAck(body []byte) {
	ctx.t.Helper()

	conn, err := amqp.Dial(ctx.rabbitURI)
	require.NoError(ctx.t, err, "connect rabbitmq")
	defer conn.Close()

	ch, err := conn.Channel()
	require.NoError(ctx.t, err, "open channel")
	defer ch.Close()

	err = ch.Confirm(false)
	require.NoError(ctx.t, err, "enable confirms")

	confirms := ch.NotifyPublish(make(chan amqp.Confirmation, 1))

	err = ch.Publish(
		"", ctx.queueName, false, false,
		amqp.Publishing{
			ContentType: "application/json",
			Body:        body,
			Headers:     amqp.Table{"X-GitHub-Event": "workflow_job"},
		},
	)
	require.NoError(ctx.t, err, "publish")

	select {
	case c := <-confirms:
		require.True(ctx.t, c.Ack, "message not acked")
	case <-time.After(10 * time.Second):
		require.Fail(ctx.t, "timeout waiting for ack")
	}
}

// getQueueDepth returns the current number of messages in the queue via passive declare.
func (ctx *testContext) getQueueDepth() int {
	ctx.t.Helper()

	conn, err := amqp.Dial(ctx.rabbitURI)
	require.NoError(ctx.t, err, "connect rabbitmq")
	defer conn.Close()

	ch, err := conn.Channel()
	require.NoError(ctx.t, err, "open channel")
	defer ch.Close()

	q, err := ch.QueueDeclarePassive(
		ctx.queueName,
		true,  // durable
		false, // auto-delete
		false, // exclusive
		false, // no-wait
		nil,
	)
	require.NoError(ctx.t, err, "declare passive queue")
	return q.Messages
}

// shutdownMain sends SIGTERM to trigger graceful shutdown in main().
func (ctx *testContext) shutdownMain() {
	ctx.t.Helper()
	_ = syscall.Kill(syscall.Getpid(), syscall.SIGTERM)
}

// createFlavor sends a create flavor request to the server
func (ctx *testContext) createFlavor(flavor, platform string, labels []string, priority int) int {
	ctx.t.Helper()

	body := map[string]any{
		"platform": platform,
		"labels":   labels,
		"priority": priority,
	}

	b, err := json.Marshal(body)
	require.NoError(ctx.t, err, "marshal payload")

	url := "http://localhost:" + ctx.port + "/api/v1/flavors/" + flavor

	resp, err := http.Post(url, "application/json", bytes.NewReader(b))
	require.NoError(ctx.t, err, "create flavor request")
	defer resp.Body.Close()

	return resp.StatusCode
}

// getFlavorPressure sends a get flavor pressure request to the server
func (ctx *testContext) getFlavorPressure(flavor string) map[string]int {
	ctx.t.Helper()

	url := "http://localhost:" + ctx.port + "/api/v1/flavors/" + flavor + "/pressure"

	resp, err := http.Get(url)
	require.NoError(ctx.t, err, "get flavor pressure request")
	defer resp.Body.Close()

	require.Equal(ctx.t, http.StatusOK, resp.StatusCode, "unexpected status getting pressure")

	var pressures map[string]int
	require.NoError(ctx.t, json.NewDecoder(resp.Body).Decode(&pressures), "decode response")

	return pressures
}

// assertFlavorPressureEquals checks that the pressures map contains the expected pressure for the given flavor
func (ctx *testContext) assertFlavorPressureEquals(pressures map[string]int, flavor string, expected int) {
	ctx.t.Helper()
	value, exists := pressures[flavor]
	assert.True(ctx.t, exists, "expected flavor %q in response, got %+v", flavor, pressures)
	assert.Equal(ctx.t, expected, value, "expected pressure %d for flavor %q, got %d", expected, flavor, value)
}

// waitForHTTP keeps trying a GET request until the server responds
// with any HTTP status (including 4xx/5xx), or until timeout elapses.
func (ctx *testContext) waitForHTTP(url string, timeout time.Duration) {
	ctx.t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		resp, err := http.Get(url)
		if err == nil {
			resp.Body.Close()
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	require.Fail(ctx.t, "server did not start responding", "server did not start responding at %s within %s", url, timeout)
}

// waitForHTTPDown waits until the server stops responding (connection errors).
func (ctx *testContext) waitForHTTPDown(url string, timeout time.Duration) {
	ctx.t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		resp, err := http.Get(url)
		if err != nil {
			return
		}
		if resp != nil {
			resp.Body.Close()
		}
		time.Sleep(100 * time.Millisecond)
	}
	require.Fail(ctx.t, "server did not stop", "server still responding at %s after %s", url, timeout)
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
