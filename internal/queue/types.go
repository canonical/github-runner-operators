/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

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

// resetChannel opens a new AMQP channel and declares the queue.
func (c *Client) resetChannel(queue string, passive bool) error {
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

	if passive {
		_, err = ch.QueueDeclarePassive(
			queue, // queueName
			true,  // durable
			false, // delete when unused
			false, // exclusive
			false, // no-wait
			nil,   // arguments
		)
	} else {
		_, err = ch.QueueDeclare(
			queue, // queueName
			true,  // durable
			false, // delete when unused
			false, // exclusive
			false, // no-wait
			nil,   // arguments
		)
	}
	if err != nil {
		return fmt.Errorf("failed to declare AMQP queue: %w", err)
	}

	return nil
}

type AmqpProducer struct {
	client    *Client
	queueName string
}

type Producer interface {
	Push(ctx context.Context, headers map[string]interface{}, msg []byte) error
}

type amqpChannel interface {
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (confirmation, error)
	IsClosed() bool
	Confirm(noWait bool) error
	QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
	QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
	Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error)
	Qos(prefetchCount, prefetchSize int, global bool) error
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

func (ch *amqpChannelWrapper) Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error) {
	return ch.Channel.Consume(queue, consumer, autoAck, exclusive, noLocal, noWait, args)
}

func (ch *amqpChannelWrapper) Qos(prefetchCount, prefetchSize int, global bool) error {
	return ch.Channel.Qos(prefetchCount, prefetchSize, global)
}

// parseToTime parses a string pointer to time.Time, returning zero time if nil or invalid.
func parseToTime(timeStr string, logger *slog.Logger) *time.Time {
	if timeStr == "" || timeStr == "null" {
		return nil
	}
	t, err := time.Parse(time.RFC3339, timeStr) // github timestamps are in ISO 8601 format
	if err != nil {
		logger.Warn("failed to parse time", "timeStr", timeStr, "error", err)
		return nil
	}
	return &t
}
