/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package queue provides custom error types for AMQP consumer implementations.
 *
 */

package queue

import "errors"

// Sentinel errors for error checking with errors.Is
var (
	ErrRetryable    = errors.New("retryable error")
	ErrNonRetryable = errors.New("non-retryable error")
)

// Custom error types for specific validation failures
var (
	ErrInvalidJSON      = errors.New("invalid JSON in message")
	ErrMissingField     = errors.New("missing required field")
	ErrInvalidHeader    = errors.New("invalid message header")
	ErrInvalidTimestamp = errors.New("invalid timestamp format")
	ErrUnknownAction    = errors.New("unknown webhook action")
	ErrJobAlreadyExists = errors.New("job already exists")
	ErrUnsupportedEvent = errors.New("unsupported event type")
)

// MessageHandlingError represents an error that occurred while handling a message,
// along with an indication of whether the message should be requeued.
type MessageHandlingError struct {
	Reason  string
	Requeue bool
	Err     error
}

// Error implements the error interface for MessageHandlingError.
func (e *MessageHandlingError) Error() string {
	return e.Reason
}

// Unwrap implements the unwrap interface for error chains.
func (e *MessageHandlingError) Unwrap() error {
	return e.Err
}

// classifyError determines whether an error should be retried based on its type.
func classifyError(err error) error {
	if err == nil {
		return nil
	}

	// Errors that should not be retried (data validation errors and already existing records)
	if errors.Is(err, ErrInvalidJSON) ||
		errors.Is(err, ErrMissingField) ||
		errors.Is(err, ErrInvalidHeader) ||
		errors.Is(err, ErrInvalidTimestamp) ||
		errors.Is(err, ErrUnknownAction) ||
		errors.Is(err, ErrJobAlreadyExists) ||
		errors.Is(err, ErrUnsupportedEvent) {
		return &MessageHandlingError{
			Reason:  err.Error(),
			Requeue: false,
			Err:     ErrNonRetryable,
		}
	}

	// All other errors should be retried (database errors, transient failures)
	return &MessageHandlingError{
		Reason:  err.Error(),
		Requeue: true,
		Err:     ErrRetryable,
	}
}
