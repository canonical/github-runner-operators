/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue_alt

import amqp "github.com/rabbitmq/amqp091-go"

type AmqpChannel interface {
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (*interface{}, error)
	IsClosed() bool
}

type AmqpConnection interface {
	Channel() (AmqpChannel, error)
}

type AmqpProducer struct {
	amqpChannel    AmqpChannel
	amqpConnection AmqpConnection
	// Add fields for AMQP connection, channel, etc.
}

type Producer interface {
	Push(ctx interface{}, headers map[string]interface{}, msg []byte) error
}

func (p *AmqpProducer) Push(ctx interface{}, headers map[string]interface{}, msg []byte) error {
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

func (p *AmqpProducer) resetChannel() error {
	c, _ := p.amqpConnection.Channel()
	p.amqpChannel = c
	return nil
}
