/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package main

import (
	"log"
	"net/http"
	"os"

	"github.com/canonical/webhook-gateway/internal/queue"
	"github.com/canonical/webhook-gateway/internal/webhook"
)

const queueName = "webhook-queue"
const webhookPath = "/webhook"
const portEnvVar = "APP_PORT"
const rabbitMQUriEnvVar = "RABBITMQ_CONNECT_STRING"
const webhookSecretEnvVar = "APP_WEBHOOK_SECRET_VALUE"

func main() {

	port, found := os.LookupEnv(portEnvVar)
	if !found {
		log.Fatalln(portEnvVar + " environment variable not set")
	}
	uri, found := os.LookupEnv(rabbitMQUriEnvVar)
	if !found {
		log.Fatalln(rabbitMQUriEnvVar + " environment variable not set")
	}
	webhookSecret, found := os.LookupEnv(webhookSecretEnvVar)
	if !found {
		log.Panicf(webhookSecretEnvVar + " environment variable not set")
	}

	p := queue.NewAmqpProducer(uri, queueName)
	handler := &webhook.Handler{
		WebhookSecret: webhookSecret,
		Producer:      p,
	}

	mux := http.NewServeMux()
	mux.HandleFunc(webhookPath, handler.Webhook)
	log.Fatal(http.ListenAndServe(":"+port, mux))
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
