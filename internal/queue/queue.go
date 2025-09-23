/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"fmt"

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

type Producer interface {
	Push(ctx context.Context, headers map[string]interface{}, msg []byte) error
}

func (p *AmqpProducer) Push(ctx context.Context, headers map[string]interface{}, msg []byte) error {
	if p.amqpConnection == nil || p.amqpConnection.IsClosed() {
		err := p.resetConnection()
		if err != nil {
			return err
		}
	}

	if p.amqpChannel == nil || p.amqpChannel.IsClosed() {
		err := p.resetChannel()
		if err != nil {
			return err
		}
	}

	confirmation, err := p.amqpChannel.PublishWithDeferredConfirm(
		"",          // exchange
		p.queueName, // routing key
		false,       // mandatory
		false,       // immediate
		amqp.Publishing{
			ContentType: "application/json",
			Body:        msg,
			Headers:     headers,
		},
	)

	if err != nil {
		return fmt.Errorf("failed to publish message: %w", err)
	}

	select {
	case <-ctx.Done():
		return ctx.Err()

	case <-confirmation.Done():
		if !confirmation.Acked() {
			return fmt.Errorf("confirmation not acknowledged")
		}
	}
	return nil
}

func (p *AmqpProducer) resetConnection() error {
	conn, err := p.connectFunc(p.uri)

	if err != nil {
		return fmt.Errorf("failed to connect to AMQP server: %w", err)
	}
	p.amqpConnection = conn
	return nil
}

func (p *AmqpProducer) resetChannel() error {
	c, err := p.amqpConnection.Channel()

	if err != nil {
		return fmt.Errorf("failed to open channel: %w", err)
	}
	p.amqpChannel = c

	err = c.Confirm(false)
	if err != nil {
		return fmt.Errorf("failed to put channel in confirm mode: %w", err)
	}

	_, err = c.QueueDeclare(
		p.queueName, // queueName
		true,        // durable
		false,       // delete when unused
		false,       // exclusive
		false,       // no-wait
		nil,         // arguments
	)
	if err != nil {
		return fmt.Errorf("failed to declare queue: %w", err)
	}
	return nil
}

func NewAmqpProducer(uri string, queueName string) *AmqpProducer {
	return &AmqpProducer{
		uri:         uri,
		queueName:   queueName,
		connectFunc: amqpConnect,
	}
}

func amqpConnect(uri string) (AmqpConnection, error) {
	amqpConnection, err := amqp.Dial(uri)
	return &AmqpConnectionWrapper{conn: amqpConnection}, err
}
