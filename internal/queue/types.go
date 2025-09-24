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

type AmqpProducer struct {
	amqpChannel    amqpChannel
	amqpConnection amqpConnection
	connectFunc    func(uri string) (amqpConnection, error)
	uri            string
	queueName      string
	mu             sync.Mutex
}

type Producer interface {
	Push(ctx context.Context, headers map[string]interface{}, msg []byte) error
}

type amqpChannel interface {
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (confirmation, error)
	IsClosed() bool
	Confirm(noWait bool) error
	QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
}

type amqpConnection interface {
	Channel() (amqpChannel, error)
	IsClosed() bool
}

type confirmation interface {
	Done() <-chan struct{}
	Acked() bool
}

type amqpConnectionWrapper struct {
	*amqp.Connection
}

func (q *amqpConnectionWrapper) Channel() (amqpChannel, error) {
	ch, err := q.Connection.Channel()
	return &amqpChannelWrapper{Channel: ch}, err
}

type amqpChannelWrapper struct {
	*amqp.Channel
}

func (ch *amqpChannelWrapper) PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (confirmation, error) {
	return ch.Channel.PublishWithDeferredConfirm(exchange, key, mandatory, immediate, msg)
}
