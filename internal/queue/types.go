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
	conn *amqp.Connection
}

func (q *AmqpConnectionWrapper) Channel() (AmqpChannel, error) {
	ch, err := q.conn.Channel()
	return &AmqpChannelWrapper{ch: ch}, err
}

func (q *AmqpConnectionWrapper) Close() error {
	return q.conn.Close()
}

func (q *AmqpConnectionWrapper) IsClosed() bool {
	return q.conn.IsClosed()
}

type AmqpDeferredConfirmationWrapper struct {
	deferredConfirmation *amqp.DeferredConfirmation
}

func (c *AmqpDeferredConfirmationWrapper) Done() <-chan struct{} {
	return c.deferredConfirmation.Done()
}

func (c *AmqpDeferredConfirmationWrapper) Acked() bool {
	return c.deferredConfirmation.Acked()
}

type AmqpChannelWrapper struct {
	ch *amqp.Channel
}

func (ch *AmqpChannelWrapper) PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (Confirmation, error) {
	deferredConfirmation, err := ch.ch.PublishWithDeferredConfirm(exchange, key, mandatory, immediate, msg)
	return &AmqpDeferredConfirmationWrapper{deferredConfirmation: deferredConfirmation}, err
}

func (ch *AmqpChannelWrapper) IsClosed() bool {
	return ch.ch.IsClosed()
}

func (ch *AmqpChannelWrapper) Confirm(noWait bool) error {
	return ch.ch.Confirm(noWait)
}

func (ch *AmqpChannelWrapper) QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return ch.ch.QueueDeclare(name, durable, autoDelete, exclusive, noWait, args)
}
