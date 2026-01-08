/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package queue provides AMQP consumer implementations for job events.
 *
 */

package queue

import (
	"context"
	"errors"
	"fmt"

	amqp "github.com/rabbitmq/amqp091-go"
)

// AmqpConsumer is an AMQP consumer for workflow job events.
type AmqpConsumer struct {
	client  *Client
	config  QueueConfig
	channel <-chan amqp.Delivery
}

// NewAmqpConsumer creates a new AmqpConsumer with the given dependencies.
func NewAmqpConsumer(uri string, config QueueConfig) *AmqpConsumer {
	return &AmqpConsumer{
		client: &Client{
			uri:         uri,
			connectFunc: amqpConnect,
		},
		config: config,
	}
}

// Pull retrieves one message from the AMQP queue.
func (c *AmqpConsumer) Pull(ctx context.Context) (amqp.Delivery, error) {
	c.client.mu.Lock() // Lock to prevent concurrent access to connection/channel object
	defer c.client.mu.Unlock()

	return c.pullMsg(ctx)
}

func (c *AmqpConsumer) pullMsg(ctx context.Context) (amqp.Delivery, error) {
	err := c.ensureChannel()
	if err != nil {
		return amqp.Delivery{}, err
	}

	select {
	case msg, ok := <-c.channel:
		if ok {
			return msg, nil
		}
		// channel is closed
		c.channel = nil
		return amqp.Delivery{}, errors.New("amqp message channel closed")
	case <-ctx.Done():
		return amqp.Delivery{}, ctx.Err()
	}
}

func (c *AmqpConsumer) ensureChannel() error {
	err := c.ensureAmqpChannel()
	if err != nil {
		return err
	}

	if c.channel != nil {
		return nil
	}

	err = c.client.amqpChannel.Qos(
		1,     // one message delivered at a time
		0,     // no specific size limit
		false, // apply to all consumers on this channel
	)
	if err != nil {
		return fmt.Errorf("cannot set amqp channel Qos: %w", err)
	}

	channel, err := c.client.amqpChannel.Consume(
		c.config.QueueName, // queue
		"",                 // consumer tag, empty string means a unique random tag will be generated
		false,              // whether rabbitmq auto-acknowledges messages
		true,               // whether only this consumer can access the queue
		false,              // no-local
		false,              // false means wait for server confirmation that consumer is registered
		nil,                // args
	)
	if err != nil {
		return fmt.Errorf("cannot consume amqp messages: %w", err)
	}
	c.channel = channel

	return nil
}

func (c *AmqpConsumer) ensureAmqpChannel() error {
	if c.client.amqpConnection == nil || c.client.amqpConnection.IsClosed() {
		err := c.client.resetConnection()
		if err != nil {
			return err
		}
	}

	if c.client.amqpChannel == nil || c.client.amqpChannel.IsClosed() {
		err := c.client.resetChannel()
		if err != nil {
			return err
		}

		err = c.client.declareExchange(c.config.ExchangeName)
		if err != nil {
			return err
		}

		err = c.client.declareQueue(c.config.QueueName)
		if err != nil {
			return err
		}

		err = c.client.bindQueue(c.config.QueueName, c.config.RoutingKey, c.config.ExchangeName)
		if err != nil {
			return err
		}
	}
	return nil
}

// Close closes the AMQP consumer connection.
func (c *AmqpConsumer) Close() error {
	return c.client.Close()
}
