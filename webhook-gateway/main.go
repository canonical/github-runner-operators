/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package main

import (
	"log"
	"net/http"
	"os"

	"github.com/canonical/mayfly/internal/queue_alt"
	"github.com/canonical/mayfly/internal/webhook"
)

const queueName = "webhook-queue"
const webhookPath = "/webhook"

func main() {

	port, found := os.LookupEnv("APP_PORT")
	if !found {
		log.Panicf("APP_PORT environment variable not set")
	}
	uri, found := os.LookupEnv("RABBITMQ_CONNECT_STRING")
	if !found {
		log.Panicf("RABBITMQ_CONNECT_STRING environment variable not set")
	}
	webhookSecret, found := os.LookupEnv("WEBHOOK_SECRET")
	if !found {
		log.Panicf("WEBHOOK_SECRET environment variable not set")
	}

	//p := queue.NewProducer(uri, queueName)

	p := queue_alt.NewAmqpProducer(uri, queueName)
	handler := &webhook.Handler{
		WebhookSecret: webhookSecret,
		Producer:      p,
	}

	http.HandleFunc(webhookPath, handler.Webhook)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
