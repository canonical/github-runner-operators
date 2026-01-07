/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestSetupDeadLetterQueue(t *testing.T) {
	/*
		arrange: Create a client with mock channel.
		act: Call setupDeadLetterQueue.
		assert: DLX exchange declared, DLQ queue declared, and queue bound to exchange.
	*/
	ch := &MockAmqpChannel{}
	client := &Client{amqpChannel: ch}

	err := client.setupDeadLetterQueue("test-dlx", "test-dlq", "test-routing-key")

	assert.NoError(t, err)
	assert.Contains(t, ch.exchangeNames, "test-dlx", "DLX exchange should be declared")
	assert.Contains(t, ch.queueNames, "test-dlq", "DLQ queue should be declared")
	assert.Equal(t, "test-dlq", ch.boundQueue)
	assert.Equal(t, "test-dlx", ch.boundExchange)
	assert.Equal(t, "test-routing-key", ch.boundRoutingKey)
}

func TestSetupDeadLetterQueueErrors(t *testing.T) {
	/*
		arrange: Create a client with mock channel configured for each error scenario.
		act: Call setupDeadLetterQueue.
		assert: Appropriate error returned.
	*/
	tests := []struct {
		name                 string
		exchangeDeclareError bool
		queueDeclareError    bool
		bindError            bool
		expectErrContains    string
	}{
		{
			name:                 "returns error when exchange declare fails",
			exchangeDeclareError: true,
			expectErrContains:    "cannot declare dead-letter exchange",
		},
		{
			name:              "returns error when queue declare fails",
			queueDeclareError: true,
			expectErrContains: "cannot declare dead-letter queue",
		},
		{
			name:              "returns error when queue bind fails",
			bindError:         true,
			expectErrContains: "cannot bind dead-letter queue",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ch := &MockAmqpChannel{
				exchangeDeclareError: tt.exchangeDeclareError,
				queueDeclareError:    tt.queueDeclareError,
				bindError:            tt.bindError,
			}
			client := &Client{amqpChannel: ch}

			err := client.setupDeadLetterQueue("test-dlx", "test-dlq", "test-routing-key")

			assert.Error(t, err)
			assert.ErrorContains(t, err, tt.expectErrContains)
		})
	}
}
