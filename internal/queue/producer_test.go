/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"errors"
	"testing"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

// TODO : Put this in a helper file because it is also used by consumer tests
type MockAmqpChannel struct {
	msgs             [][]byte
	headers          []map[string]interface{}
	isclosed         bool
	confirmMode      bool
	queueName        string
	exchangeName     string
	queueDurable     bool
	confirmModeError bool
	// Publish error modes
	publishError bool
	publishNoAck bool
	publishHangs bool
	// Declaration error modes
	exchangeDeclareError bool
	queueDeclareError    bool
	// Binding tracking
	boundQueue      string
	boundExchange   string
	boundRoutingKey string
	bindError       bool
}

func (ch *MockAmqpChannel) PublishWithDeferredConfirm(exchange string, key string, _, _ bool, msg amqp.Publishing) (confirmation, error) {
	if ch.publishError {
		return nil, errors.New("publish error")
	}
	ch.msgs = append(ch.msgs, msg.Body)
	ch.headers = append(ch.headers, msg.Headers)

	done_ch := make(chan struct{}, 1)

	if !ch.publishHangs {
		done_ch <- struct{}{}
	}

	ack := !ch.publishNoAck
	confirmation := &MockConfirmation{
		done: done_ch,
		ack:  ack,
	}
	return confirmation, nil
}

func (ch *MockAmqpChannel) IsClosed() bool {
	return ch.isclosed
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
	return nil
}

func (ch *MockAmqpChannel) QueueDeclare(name string, durable, _, _, _ bool, _ amqp.Table) (amqp.Queue, error) {
	if ch.queueDeclareError {
		return amqp.Queue{}, errors.New("queue declare error")
	}
	ch.queueName = name
	ch.queueDurable = durable
	return amqp.Queue{}, nil
}

func (ch *MockAmqpChannel) QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return amqp.Queue{}, nil
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
	return nil, nil
}

func (ch *MockAmqpChannel) Qos(prefetchCount, prefetchSize int, global bool) error {
	return nil
}

func (ch *MockAmqpChannel) Close() error {
	ch.isclosed = true
	return nil
}

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

type MockAmqpConnection struct {
	channelCalls         int
	amqpChannel          *MockAmqpChannel
	isclosed             bool
	errMode              bool
	confirmModeError     bool
	exchangeDeclareError bool
}

func (m *MockAmqpConnection) Channel() (amqpChannel, error) {
	if m.errMode {
		return nil, errors.New("failed to open channel")
	}
	m.channelCalls++
	m.amqpChannel = &MockAmqpChannel{
		confirmModeError:     m.confirmModeError,
		exchangeDeclareError: m.exchangeDeclareError,
	}
	return m.amqpChannel, nil
}

func (m *MockAmqpConnection) IsClosed() bool {
	return m.isclosed
}

func (m *MockAmqpConnection) Close() error {
	m.isclosed = true
	return nil
}

func TestPush(t *testing.T) {
	/*
		arrange: create a producer with a fake amqp connection
		act: push a message to the queue
		assert: message was published to the amqp channel
	*/
	mockAmqpChannel := &MockAmqpChannel{}
	amqpProducer := &AmqpProducer{
		client: &Client{
			amqpChannel: mockAmqpChannel,
			amqpConnection: &MockAmqpConnection{
				amqpChannel: mockAmqpChannel,
			},
		},
		config: DefaultQueueConfig(),
	}

	headers := map[string]interface{}{"header1": "value1"}
	amqpProducer.Push(context.Background(), headers, []byte("TestMessage"))

	assert.Contains(t, mockAmqpChannel.headers, headers)
	assert.Contains(t, mockAmqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
}

func TestPushFailure(t *testing.T) {
	/*
		arrange: create a producer with a fake confirm handler that always fails
		act: push a message to the queue that will fail to publish
		assert: the push return an error
	*/
	tests := []struct {
		name        string
		mockChannel *MockAmqpChannel
		context     context.Context
		errMsg      string
	}{
		{
			name:        "message is not acked",
			mockChannel: &MockAmqpChannel{publishNoAck: true},
			errMsg:      "confirmation not acknowledged",
			context:     context.Background(),
		},
		{
			name: "context is done",
			context: func() context.Context {
				ctx, cancel := context.WithCancel(context.Background())
				cancel()
				return ctx
			}(),
			mockChannel: &MockAmqpChannel{publishHangs: true},
			errMsg:      "context canceled",
		},
		{
			name:        "publish returns error",
			mockChannel: &MockAmqpChannel{publishError: true},
			errMsg:      "publish error",
			context:     context.Background(),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			amqpProducer := &AmqpProducer{
				client: &Client{
					amqpChannel: tt.mockChannel,
					amqpConnection: &MockAmqpConnection{
						amqpChannel: tt.mockChannel,
					},
				},
				config: DefaultQueueConfig(),
			}

			err := amqpProducer.Push(tt.context, nil, []byte("TestMessage"))

			assert.Error(t, err, "expected error when message fails to publish")
			assert.ErrorContains(t, err, tt.errMsg)
		})
	}
}

func TestPushNoChannel(t *testing.T) {
	/*
		arrange: create a queue with no amqp channel
		act: push a message to the queue
		assert: connection got re-established and message was published to the amqp channel
	*/
	tests := []struct {
		name    string
		channel amqpChannel
	}{
		{
			name:    "channel is nil",
			channel: nil,
		},
		{
			name: "channel is closed",
			channel: &MockAmqpChannel{
				isclosed: true,
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockAmqpConnection := &MockAmqpConnection{}
			amqpProducer := &AmqpProducer{
				client: &Client{
					amqpChannel:    tt.channel,
					amqpConnection: mockAmqpConnection,
				},
				config: DefaultQueueConfig(),
			}

			amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
			assert.Equal(t, 1, mockAmqpConnection.channelCalls, "expected connection to be re-established")
			assert.Contains(t, mockAmqpConnection.amqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
		})
	}
}

func TestPushNoChannelFailure(t *testing.T) {
	/*
		arrange: create a queue with no amqp channel where the channel function fails
		act: push a message to the queue
		assert: push returns an error
	*/
	mockAmqpConnection := &MockAmqpConnection{
		amqpChannel: nil,
		errMode:     true,
	}
	amqpProducer := &AmqpProducer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		config: DefaultQueueConfig(),
	}
	err := amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
	assert.Error(t, err, "expected error when channel fails to open")
	assert.ErrorContains(t, err, "failed to open channel")
}

func TestPushNoConnection(t *testing.T) {
	/*
		arrange: create a queue with no amqp connection
		act: push a message to the queue
		assert: connection got established and message was published to the amqp channel
	*/
	tests := []struct {
		name       string
		connection amqpConnection
	}{
		{
			name:       "connection is nil",
			connection: nil,
		},
		{
			name: "connection is closed",
			connection: &MockAmqpConnection{
				isclosed: true,
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockAmqpConnection := &MockAmqpConnection{
				amqpChannel: &MockAmqpChannel{},
			}
			amqpProducer := &AmqpProducer{
				client: &Client{
					amqpConnection: tt.connection,
					uri:            "amqp://guest:guest@localhost:5672/",
					connectFunc: func(uri string) (amqpConnection, error) {
						return mockAmqpConnection, nil
					},
				},
				config: DefaultQueueConfig(),
			}

			amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
			assert.Equal(t, 1, mockAmqpConnection.channelCalls, "expected connection to be re-established")
			assert.Contains(t, mockAmqpConnection.amqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
		})
	}
}

func TestPushNoConnectionFailure(t *testing.T) {
	/*
		arrange: create a queue with no amqp connection where the connect function fails
		act: push a message to the queue
		assert: push returns an error
	*/
	amqpProducer := &AmqpProducer{
		client: &Client{
			amqpConnection: nil,
			uri:            "amqp://guest:guest@localhost:5672/",
			connectFunc: func(uri string) (amqpConnection, error) {
				return nil, errors.New("connection error")
			},
		},
		config: DefaultQueueConfig(),
	}

	err := amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
	assert.Error(t, err, "expected error when connection fails")
	assert.ErrorContains(t, err, "connection error")
}

func TestPushExchangeDeclare(t *testing.T) {
	/*
		arrange: create a producer with no amqp channel
		act: push a message to the queue
		assert: channel with confirm mode is established and exchange is declared with config name
	*/
	mockAmqpConnection := &MockAmqpConnection{}
	config := DefaultQueueConfig()
	amqpProducer := &AmqpProducer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		config: config,
	}

	amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))

	assert.True(t, mockAmqpConnection.amqpChannel.confirmMode, "expected channel to be in confirm mode")
	assert.Equal(t, config.ExchangeName, mockAmqpConnection.amqpChannel.exchangeName, "expected exchange name to be "+config.ExchangeName)
}

func TestPushExchangeDeclareFailure(t *testing.T) {
	/*
		arrange: create a producer with no amqp channel where the exchange declare fails
		act: push a message to the queue
		assert: push returns an error
	*/
	tests := []struct {
		name               string
		mockAmqpConnection *MockAmqpConnection
		errMsg             string
	}{
		{
			name:               "exchange declare error",
			mockAmqpConnection: &MockAmqpConnection{exchangeDeclareError: true},
			errMsg:             "exchange declare error",
		},
		{
			name: "confirm error",
			mockAmqpConnection: &MockAmqpConnection{
				confirmModeError: true,
			},
			errMsg: "confirm error",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			amqpProducer := &AmqpProducer{
				client: &Client{
					amqpChannel:    nil,
					amqpConnection: tt.mockAmqpConnection,
				},
				config: DefaultQueueConfig(),
			}

			err := amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))

			assert.Error(t, err, "expected error when exchange declare fails")
			assert.ErrorContains(t, err, tt.errMsg)
		})
	}
}
