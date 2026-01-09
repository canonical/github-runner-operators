/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"errors"

	amqp "github.com/rabbitmq/amqp091-go"
)

// MockAmqpChannel implements amqpChannel for unit testing.
type MockAmqpChannel struct {
	// Message tracking
	msgs    [][]byte
	headers []map[string]interface{}

	// State
	isclosed    bool
	isClosedRet bool
	closeCalls  int
	closeErr    error
	confirmMode bool

	// Declaration tracking
	queueName     string
	exchangeName  string
	queueDurable  bool
	queueArgs     amqp.Table
	declareCount  int
	exchangeNames []string
	queueNames    []string
	exchangeCount int

	// Binding tracking
	boundQueue      string
	boundExchange   string
	boundRoutingKey string

	// Publish behavior
	publishError bool
	publishNoAck bool
	publishHangs bool

	// Error modes
	confirmModeError     bool
	exchangeDeclareError bool
	queueDeclareError    bool
	bindError            bool

	// Consumer support
	consumeCh  <-chan amqp.Delivery
	consumeErr error
	qosErr     error

	// Additional error modes for types_test
	queueDeclarePassiveErr error
}

func (ch *MockAmqpChannel) PublishWithDeferredConfirm(exchange string, key string, _, _ bool, msg amqp.Publishing) (confirmation, error) {
	if ch.publishError {
		return nil, errors.New("publish error")
	}
	ch.msgs = append(ch.msgs, msg.Body)
	ch.headers = append(ch.headers, msg.Headers)

	doneCh := make(chan struct{}, 1)

	if !ch.publishHangs {
		doneCh <- struct{}{}
	}

	ack := !ch.publishNoAck
	conf := &MockConfirmation{
		done: doneCh,
		ack:  ack,
	}
	return conf, nil
}

func (ch *MockAmqpChannel) IsClosed() bool {
	return ch.isclosed || ch.isClosedRet
}

func (ch *MockAmqpChannel) Confirm(_ bool) error {
	if ch.confirmModeError {
		return errors.New("confirm error")
	}
	ch.confirmMode = true
	return nil
}

func (ch *MockAmqpChannel) ExchangeDeclare(name string, _ string, _, _, _, _ bool, _ amqp.Table) error {
	if ch.exchangeDeclareError {
		return errors.New("exchange declare error")
	}
	ch.exchangeName = name
	ch.exchangeNames = append(ch.exchangeNames, name)
	ch.exchangeCount++
	return nil
}

func (ch *MockAmqpChannel) QueueDeclare(name string, durable, _, _, _ bool, args amqp.Table) (amqp.Queue, error) {
	if ch.queueDeclareError {
		return amqp.Queue{}, errors.New("queue declare error")
	}
	ch.queueName = name
	ch.queueDurable = durable
	ch.queueArgs = args
	ch.queueNames = append(ch.queueNames, name)
	ch.declareCount++
	return amqp.Queue{Name: name}, nil
}

func (ch *MockAmqpChannel) QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return amqp.Queue{Name: name}, ch.queueDeclarePassiveErr
}

func (ch *MockAmqpChannel) QueueBind(name, key, exchange string, noWait bool, args amqp.Table) error {
	if ch.bindError {
		return errors.New("bind error")
	}
	ch.boundQueue = name
	ch.boundRoutingKey = key
	ch.boundExchange = exchange
	return nil
}

func (ch *MockAmqpChannel) Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error) {
	return ch.consumeCh, ch.consumeErr
}

func (ch *MockAmqpChannel) Qos(prefetchCount, prefetchSize int, global bool) error {
	return ch.qosErr
}

func (ch *MockAmqpChannel) Close() error {
	ch.closeCalls++
	ch.isclosed = true
	return ch.closeErr
}

// MockConfirmation implements confirmation for unit testing.
type MockConfirmation struct {
	done <-chan struct{}
	ack  bool
}

func (c *MockConfirmation) Done() <-chan struct{} {
	return c.done
}

func (c *MockConfirmation) Acked() bool {
	return c.ack
}

// MockAmqpConnection implements amqpConnection for unit testing.
type MockAmqpConnection struct {
	channelCalls         int
	amqpChannel          *MockAmqpChannel
	channel              amqpChannel
	channelErr           error
	isclosed             bool
	isClosedRet          bool
	closeCalls           int
	closeErr             error
	errMode              bool
	confirmModeError     bool
	exchangeDeclareError bool
}

func (m *MockAmqpConnection) Channel() (amqpChannel, error) {
	if m.errMode {
		return nil, errors.New("failed to open channel")
	}
	if m.channelErr != nil {
		return nil, m.channelErr
	}
	if m.channel != nil {
		return m.channel, nil
	}
	m.channelCalls++
	m.amqpChannel = &MockAmqpChannel{
		confirmModeError:     m.confirmModeError,
		exchangeDeclareError: m.exchangeDeclareError,
	}
	return m.amqpChannel, nil
}

func (m *MockAmqpConnection) IsClosed() bool {
	return m.isclosed || m.isClosedRet
}

func (m *MockAmqpConnection) Close() error {
	m.closeCalls++
	m.isclosed = true
	return m.closeErr
}
