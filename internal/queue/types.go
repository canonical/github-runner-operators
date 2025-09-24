/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"sync"

	amqp "github.com/rabbitmq/amqp091-go"
)

type AmqpChannel interface {
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (Confirmation, error)
	IsClosed() bool
	Confirm(noWait bool) error
	QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
}

type AmqpConnection interface {
	Channel() (AmqpChannel, error)
	IsClosed() bool
}

type Confirmation interface {
	Done() <-chan struct{}
	Acked() bool
}

type AmqpProducer struct {
	amqpChannel    AmqpChannel
	amqpConnection AmqpConnection
	connectFunc    func(uri string) (AmqpConnection, error)
	uri            string
	queueName      string
	mu             sync.Mutex
}

type Producer interface {
	Push(ctx context.Context, headers map[string]interface{}, msg []byte) error
}

type AmqpConnectionWrapper struct {
	*amqp.Connection
}

func (q *AmqpConnectionWrapper) Channel() (AmqpChannel, error) {
	ch, err := q.Connection.Channel()
	return &AmqpChannelWrapper{Channel: ch}, err
}

type AmqpChannelWrapper struct {
	*amqp.Channel
}

func (ch *AmqpChannelWrapper) PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (Confirmation, error) {
	return ch.Channel.PublishWithDeferredConfirm(exchange, key, mandatory, immediate, msg)
}
