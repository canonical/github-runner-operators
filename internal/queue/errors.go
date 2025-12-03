/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package queue provides custom error types for AMQP consumer implementations.
 *
 */

package queue

// MessageHandlingError represents an error that occurred while handling a message,
// along with an indication of whether the message should be requeued.
type MessageHandlingError struct {
	Reason  string
	Requeue bool
}

// Error implements the error interface for MessageHandlingError.
func (e *MessageHandlingError) Error() string {
	return e.Reason
}

// NoRetryableError creates a MessageHandlingError indicating the message should not be requeued.
func NoRetryableError(reason string) error {
	return &MessageHandlingError{
		Reason:  reason,
		Requeue: false,
	}
}

// RetryableError creates a MessageHandlingError indicating the message should be requeued.
func RetryableError(reason string) error {
	return &MessageHandlingError{
		Reason:  reason,
		Requeue: true,
	}
}
