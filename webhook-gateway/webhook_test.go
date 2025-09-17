/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

// integration test for the webhook-gateway application

package main

import (
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

func TestHTTPRequestisForwarded(t *testing.T) {
	if !*integration {
		t.Skip("skipping integration test")
	}
	os.Setenv("APP_PORT", "8080")
	os.Setenv("RABBITMQ_CONNECT_STRING", "amqp://guest:guest@localhost:5672/")
	os.Setenv("WEBHOOK_SECRET", "fake-secret")
	// start the server
	go main()
	body := `{"message":"Hello, Alice!"}`
	headers := map[string]string{
		"X-Hub-Signature-256": "0aca2d7154cddad4f56f246cad61f1485df34b8056e10c4e4799494376fb3413",
		"Content-Type":        "application/json",
	}
	req, err := http.NewRequest("POST", "http://localhost:8080/webhook", strings.NewReader(body))
	if err != nil {
		t.Fatalf("Failed to create request: %v", err)
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	// Create an HTTP client
	client := &http.Client{}

	// add a retry loop to wait for the server to start
	var resp *http.Response
	for i := 0; i < 5; i++ {
		resp, err = client.Do(req)
		if err == nil {
			break
		}
		t.Logf("Retrying... (%d/5)", i+1)
		// wait 2**i seconds before retrying
		time.Sleep(time.Duration((1 << i) * time.Second))
	}
	if err != nil {
		t.Fatalf("Failed to send request: %v. Server did probably not start up.", err)
	}
	defer resp.Body.Close()

	// check that message is in the queue
	uri, found := os.LookupEnv("RABBITMQ_CONNECT_STRING")
	if !found {
		t.Fatalf("RABBITMQ_CONNECT_STRING environment variable not set")
	}
	conn, err := amqp.Dial(uri)
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

	msg := <-deliveryChan

	assert.Equal(t, body, string(msg.Body), "expected message body to match")
}
