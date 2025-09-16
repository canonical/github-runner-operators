/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package main

import (
	"log"
	"net/http"
	"os"

	"github.com/canonical/mayfly/internal/queue"
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

	q := queue.NewAmqpQueue(uri, queueName)
	q.StartProducer()

	webhook.InitQueue(q)
	webhook.InitWebhookSecret(webhookSecret)

	http.HandleFunc(webhookPath, webhook.WebhookHandler)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
