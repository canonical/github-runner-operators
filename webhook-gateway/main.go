package main

import (
	"log"
	"net/http"

	"github.com/canonical/mayfly/internal/queue"
	"github.com/canonical/mayfly/internal/webhook"
)

func main() {
	uri := "amqp://guest:guest@localhost:5672/"
	queueName := "webhook-queue"

	q := queue.NewAmqpQueue(uri, queueName)
	q.StartProducer()

	webhook.InitQueue(q)
	webhook.InitWebhookSecret("fake-secret")

	http.HandleFunc("/webhook", webhook.WebhookHandler)
	log.Fatal(http.ListenAndServe(":8080", nil))
}
