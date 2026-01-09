/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import "fmt"

// ensureDeadLetterQueue declares the dead-letter exchange and queue, and binds them together.
// This is an idempotent operation that encapsulates the RabbitMQ-specific dead-letter configuration.
func (c *Client) ensureDeadLetterQueue(dlxName, dlqName, routingKey string) error {
	err := c.ensureExchange(dlxName)
	if err != nil {
		return fmt.Errorf("cannot declare dead-letter exchange: %w", err)
	}

	err = c.ensureQueue(dlqName)
	if err != nil {
		return fmt.Errorf("cannot declare dead-letter queue: %w", err)
	}

	err = c.ensureQueueBinding(dlqName, routingKey, dlxName)
	if err != nil {
		return fmt.Errorf("cannot bind dead-letter queue: %w", err)
	}

	return nil
}
