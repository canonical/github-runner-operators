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
	p.client.mu.Lock() // Lock to prevent concurrent access to connection/channel object
	err := p.resetConnectionOrChannelIfNecessary()
	if err != nil {
		p.client.mu.Unlock()
		return err
	}

	msgConfirmation, err := p.publishMsg(msg, headers)
	if err != nil {
		p.client.mu.Unlock()
		return err
	}
	p.client.mu.Unlock() // Unlock to not unblock other Push calls while waiting for confirmation
	err = waitForMsgConfirmation(ctx, msgConfirmation)

	return err
}

func (p *AmqpProducer) resetConnectionOrChannelIfNecessary() error {
	if p.client.amqpConnection == nil || p.client.amqpConnection.IsClosed() {
		err := p.client.resetConnection()
		if err != nil {
			return err
		}
	}

	if p.client.amqpChannel == nil || p.client.amqpChannel.IsClosed() {
		err := p.client.resetChannel()
		if err != nil {
			return err
		}

		err = p.client.declareExchange(p.exchangeName)
		if err != nil {
			return err
		}
	}
	return nil
}

func waitForMsgConfirmation(ctx context.Context, confirmation confirmation) error {
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

func (p *AmqpProducer) publishMsg(msg []byte, headers map[string]interface{}) (confirmation, error) {
	confirmation, err := p.client.amqpChannel.PublishWithDeferredConfirm(
		"",             // exchange
		p.exchangeName, // routing key
		false,          // mandatory
		false,          // immediate
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

func NewAmqpProducer(uri string, queueName string) *AmqpProducer {
	return &AmqpProducer{
		client: &Client{
			uri:         uri,
			connectFunc: amqpConnect,
		},
		exchangeName: queueName,
	}
}

func amqpConnect(uri string) (amqpConnection, error) {
	amqpConnection, err := amqp.Dial(uri)
	return &amqpConnectionWrapper{Connection: amqpConnection}, err
}
