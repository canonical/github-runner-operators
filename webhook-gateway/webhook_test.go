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
	"flag"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

var integration = flag.Bool("integration", false, "Run integration tests")

func TestHTTPRequestIsForwarded(t *testing.T) {
	if !*integration {
		t.Skip("skipping integration test")
	}
	const payload = `{"message":"Hello, Bob!"}`

	go main()

	secret := getSecretFromEnv(t)
	doPostRequest(t, payload, secret)

	amqpUri := getAmqpUriFromEnv(t)
	msg := consumeMessage(t, amqpUri)

	assert.Equal(t, payload, msg, "expected message body to match")
}

func getSecretFromEnv(t *testing.T) string {
	secret := os.Getenv("WEBHOOK_SECRET")
	if secret == "" {
		t.Fatal("WEBHOOK_SECRET environment variable not set")
	}
	return secret
}

func getAmqpUriFromEnv(t *testing.T) string {
	uri := os.Getenv("RABBITMQ_CONNECT_STRING")
	if uri == "" {
		t.Fatal("RABBITMQ_CONNECT_STRING environment variable not set")
	}
	return uri
}

func doPostRequest(t *testing.T, payload string, secret string) {
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

	client := &http.Client{}

	var resp *http.Response
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

func createSignature(message string, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write([]byte(message))
	return hex.EncodeToString(h.Sum(nil))
}

func consumeMessage(t *testing.T, amqpUri string) string {
	conn, err := amqp.Dial(amqpUri)
	if err != nil {
		t.Fatalf("Failed to connect to RabbitMQ: %v", err)
	}
	defer conn.Close()
	ch, err := conn.Channel()
	if err != nil {
		t.Fatalf("Failed to open a channel: %v", err)
	}
	defer ch.Close()

	_, err = ch.QueueDeclare(
		"webhook-queue", // name
		true,            // durable
		false,           // delete when unused
		false,           // exclusive
		false,           // no-wait
		nil,             // arguments
	)

	if err != nil {
		t.Fatalf("Failed to declare a queue: %v", err)
	}

	deliveryChan, err := ch.Consume("webhook-queue", "", true, false, false, false, nil)

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
