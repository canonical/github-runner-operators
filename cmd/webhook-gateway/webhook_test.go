//go:build integration

/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

// integration test for the webhook-gateway application

package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/queue"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

func TestHTTPRequestIsForwarded(t *testing.T) {
	const payload = `{"message":"Hello, Bob!"}`
	amqpUri := getAmqpUriFromEnv(t)

	setupQueue(t, amqpUri)

	go main()

	secret := getSecretFromEnv(t)
	sendPayloadToHTTPServer(t, payload, secret)

	msg := consumeMessage(t, amqpUri)

	assert.Equal(t, payload, msg, "expected message body to match")
}

func getSecretFromEnv(t *testing.T) string {
	secret := os.Getenv(webhookSecretEnvVar)
	if secret == "" {
		t.Fatal(webhookSecretEnvVar + " environment variable not set")
	}
	return secret
}

func getAmqpUriFromEnv(t *testing.T) string {
	uri := os.Getenv(rabbitMQUriEnvVar)
	if uri == "" {
		t.Fatal(webhookSecretEnvVar + " environment variable not set")
	}
	return uri
}

func sendPayloadToHTTPServer(t *testing.T, payload string, secret string) {
	req := createRequest(t, payload, secret)
	postRequestUsingRetryBecauseServerMightNotYetBeUp(t, req)
}

func postRequestUsingRetryBecauseServerMightNotYetBeUp(t *testing.T, req *http.Request) {
	client := &http.Client{}

	var resp *http.Response
	var err error
	for i := 0; i < 5; i++ {
		resp, err = client.Do(req)
		if err == nil {
			break
		}
		t.Logf("Retrying... (%d/5)", i+1)
		time.Sleep(time.Duration((1 << i) * time.Second))
	}
	if err != nil {
		t.Fatalf("Failed to send request: %v. Server did probably not start up.", err)
	}
	defer resp.Body.Close()
}

func createRequest(t *testing.T, payload string, secret string) *http.Request {
	headers := map[string]string{
		"X-Hub-Signature-256": createSignature(payload, secret),
		"Content-Type":        "application/json",
	}
	req, err := http.NewRequest("POST", "http://localhost:8080/webhook", strings.NewReader(payload))
	if err != nil {
		t.Fatalf("Failed to create request: %v", err)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	return req
}

func createSignature(message string, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write([]byte(message))
	return "sha256=" + hex.EncodeToString(h.Sum(nil))
}

// returns an AMQP channel and a cleanup function to close the connection and channel
func setupAMQPChannel(t *testing.T, amqpUri string) (*amqp.Channel, func()) {
	conn, err := amqp.Dial(amqpUri)
	if err != nil {
		t.Fatalf("Failed to connect to RabbitMQ: %v", err)
	}

	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		t.Fatalf("Failed to open a channel: %v", err)
	}

	cleanup := func() {
		ch.Close()
		conn.Close()
	}

	return ch, cleanup
}

// setupQueue declares the exchange, queue, and binding for the test
// this is required because the webhook-gateway does not create the queue and
// published messages could be discarded if the queue does not exist
func setupQueue(t *testing.T, amqpUri string) {
	ch, cleanup := setupAMQPChannel(t, amqpUri)
	defer cleanup()

	config := queue.DefaultQueueConfig()

	err := ch.ExchangeDeclare(
		config.ExchangeName, // name)
		"direct",            // type
		true,                // durable
		false,               // auto-deleted
		false,               // internal
		false,               // no-wait
		nil,                 // arguments
	)

	if err != nil {
		t.Fatalf("Failed to declare an exchange: %v", err)
	}
	_, err = ch.QueueDeclare(
		config.QueueName, // name
		true,             // durable
		false,            // delete when unused
		false,            // exclusive
		false,            // no-wait
		nil,              // arguments
	)

	if err != nil {
		t.Fatalf("Failed to declare a queue: %v", err)
	}

	err = ch.QueueBind(
		config.QueueName,    // queue name
		config.RoutingKey,   // routing key
		config.ExchangeName, // exchange
		false,
		nil,
	)

	if err != nil {
		t.Fatalf("Failed to bind a queue: %v", err)
	}
}

func consumeMessage(t *testing.T, amqpUri string) string {
	ch, cleanup := setupAMQPChannel(t, amqpUri)
	defer cleanup()

	config := queue.DefaultQueueConfig()

	deliveryChan, err := ch.Consume(config.QueueName, "", true, false, false, false, nil)

	if err != nil {
		t.Fatalf("Failed to register a consumer: %v", err)
	}

	var msg amqp.Delivery
	select {
	case <-time.After(10 * time.Second):
		t.Fatal("Timeout waiting for message")
	case msg = <-deliveryChan:
	}

	return string(msg.Body)
}
