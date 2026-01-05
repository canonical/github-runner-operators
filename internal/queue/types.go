/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"fmt"
	"sync"

	amqp "github.com/rabbitmq/amqp091-go"
)

type Client struct {
	amqpChannel    amqpChannel
	amqpConnection amqpConnection
	connectFunc    func(uri string) (amqpConnection, error)
	uri            string
	mu             sync.Mutex
}

// resetConnection establishes a new AMQP connection.
func (c *Client) resetConnection() error {
	if c.amqpConnection != nil && !c.amqpConnection.IsClosed() {
		return nil
	}
	conn, err := c.connectFunc(c.uri)
	if err != nil {
		return fmt.Errorf("failed to connect to AMQP server: %w", err)
	}
	c.amqpConnection = conn
	return nil
}

// resetChannel opens a new AMQP channel
func (c *Client) resetChannel() error {
	if c.amqpChannel != nil && !c.amqpChannel.IsClosed() {
		return nil
	}

	ch, err := c.amqpConnection.Channel()
	if err != nil {
		return fmt.Errorf("failed to open AMQP channel: %w", err)
	}
	c.amqpChannel = ch

	err = ch.Confirm(false)
	if err != nil {
		return fmt.Errorf("failed to put channel in confirm mode: %w", err)
	}

	return nil
}

func (c *Client) declareExchange(exchangeName string) error {
	err := c.amqpChannel.ExchangeDeclare(
		exchangeName,
		"direct", // use direct exchange
		true,     // durable - don't delete on broker restart
		false,    // autoDelete - don't delete when no longer in use
		false,    // internal set to false - be suitable for publishing
		false,    // wait for confirmation
		nil,      // no additional arguments
	)
	if err != nil {
		return fmt.Errorf("failed to declare AMQP exchange: %w", err)
	}
	return nil
}

func (c *Client) declareQueue(queueName string) error {
	_, err := c.amqpChannel.QueueDeclare(
		queueName,
		true,  // durable
		false, // delete when unused
		false, // exclusive
		false, // no-wait
		nil,   // arguments
	)
	if err != nil {
		return fmt.Errorf("failed to declare AMQP queue: %w", err)
	}
	return nil
}

// Close gracefully closes the AMQP channel and connection.
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	var firstErr error

	if c.amqpChannel != nil && !c.amqpChannel.IsClosed() {
		if err := c.amqpChannel.Close(); err != nil {
			firstErr = err
		}
	}

	if c.amqpConnection != nil && !c.amqpConnection.IsClosed() {
		if err := c.amqpConnection.Close(); err != nil && firstErr == nil {
			firstErr = err
		}
	}

	return firstErr
}

type AmqpProducer struct {
	client       *Client
	exchangeName string
}

type Producer interface {
	Push(ctx context.Context, headers map[string]interface{}, msg []byte) error
}

type amqpChannel interface {
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (confirmation, error)
	IsClosed() bool
	Close() error
	Confirm(noWait bool) error
	ExchangeDeclare(name string, kind string, durable, autoDelete, internal, noWait bool, args amqp.Table) error
	QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
	QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
	Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error)
	Qos(prefetchCount, prefetchSize int, global bool) error
}

type amqpConnection interface {
	Channel() (amqpChannel, error)
	IsClosed() bool
	Close() error
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

func (ch *amqpChannelWrapper) Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error) {
	return ch.Channel.Consume(queue, consumer, autoAck, exclusive, noLocal, noWait, args)
}

func (ch *amqpChannelWrapper) Qos(prefetchCount, prefetchSize int, global bool) error {
	return ch.Channel.Qos(prefetchCount, prefetchSize, global)
}

type Consumer interface {
	Pull(ctx context.Context) (amqp.Delivery, error)
	Close() error
}
