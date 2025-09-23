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

func (p *AmqpProducer) Push(ctx context.Context, headers map[string]interface{}, msg []byte) error {
	p.mu.Lock()
	err := p.resetConnectionOrChannelIfNecessary()
	if err != nil {
		p.mu.Unlock()
		return err
	}

	confirmation, err := p.publishMsg(msg, headers)
	if err != nil {
		p.mu.Unlock()
		return err
	}
	p.mu.Unlock()
	err = waitForMsgConfirmation(ctx, confirmation)

	return err
}

func (p *AmqpProducer) resetConnectionOrChannelIfNecessary() error {
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
	return nil
}

func waitForMsgConfirmation(ctx context.Context, confirmation Confirmation) error {
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

func (p *AmqpProducer) publishMsg(msg []byte, headers map[string]interface{}) (Confirmation, error) {
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
		return nil, fmt.Errorf("failed to publish message: %w", err)
	}
	return confirmation, nil
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
