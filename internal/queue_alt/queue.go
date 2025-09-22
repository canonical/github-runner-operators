/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue_alt

import (
	amqp "github.com/rabbitmq/amqp091-go"
)

type AmqpChannel interface {
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (*interface{}, error)
	IsClosed() bool
	Confirm(noWait bool) error
	QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
}

type AmqpConnection interface {
	Channel() (AmqpChannel, error)
	IsClosed() bool
}

type AmqpProducer struct {
	amqpChannel    AmqpChannel
	amqpConnection AmqpConnection
	connectFunc    func(uri string) (AmqpConnection, error)
	uri            string
	name           string
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
	p.amqpChannel.PublishWithDeferredConfirm(
		"",    // exchange
		"",    // routing key
		false, // mandatory
		false, // immediate
		amqp.Publishing{
			ContentType: "application/json",
			Body:        msg,
			Headers:     headers,
		},
	)
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
		p.name, // name
		true,   // durable
		false,  // delete when unused
		false,  // exclusive
		false,  // no-wait
		nil,    // arguments
	)
	return nil
}
