/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue_alt

import (
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
	Push(ctx interface{}, headers map[string]interface{}, msg []byte) error
}

func (p *AmqpProducer) Push(ctx interface{}, headers map[string]interface{}, msg []byte) error {
	if p.amqpConnection == nil || p.amqpConnection.IsClosed() {
		p.resetConnection()
	}

	if p.amqpChannel == nil || p.amqpChannel.IsClosed() {
		p.resetChannel()
	}

	confirmation, _ := p.amqpChannel.PublishWithDeferredConfirm(
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

	select {
	case <-confirmation.Done():
	}
	return nil
}

func (p *AmqpProducer) resetConnection() error {
	conn, _ := p.connectFunc(p.uri)
	p.amqpConnection = conn
	return nil
}

func (p *AmqpProducer) resetChannel() error {
	c, _ := p.amqpConnection.Channel()
	p.amqpChannel = c

	c.Confirm(false)

	c.QueueDeclare(
		p.queueName, // queueName
		true,        // durable
		false,       // delete when unused
		false,       // exclusive
		false,       // no-wait
		nil,         // arguments
	)
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
