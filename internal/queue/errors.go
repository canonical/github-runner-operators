/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package queue provides custom error types for AMQP consumer implementations.
 *
 */

package queue

type MessageHandlingError struct {
	Reason  string
	Requeue bool
}

func (e *MessageHandlingError) Error() string {
	return e.Reason
}

func NoRequeue(reason string) error {
	return &MessageHandlingError{
		Reason:  reason,
		Requeue: false,
	}
}

func Requeue(reason string) error {
	return &MessageHandlingError{
		Reason:  reason,
		Requeue: true,
	}
}
