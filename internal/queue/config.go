/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

// Default AMQP configuration values.
const (
	defaultExchangeName = "github-workflow-jobs"
	defaultQueueName    = "github-workflow-jobs"
	defaultRoutingKey   = "workflow-job"
)

// QueueConfig holds AMQP exchange, queue, and routing configuration.
type QueueConfig struct {
	ExchangeName string
	QueueName    string
	RoutingKey   string
}

// DefaultQueueConfig returns a QueueConfig with default values.
func DefaultQueueConfig() QueueConfig {
	return QueueConfig{
		ExchangeName: defaultExchangeName,
		QueueName:    defaultQueueName,
		RoutingKey:   defaultRoutingKey,
	}
}
