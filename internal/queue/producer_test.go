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

const exchangeName = "test-exchange"
const exchangeWithDeclareError = "exchange-with-declare-error"

const exchangeWithPublishNoAck = "exchange-with-publish-no-ack"
const exchangeWithPublishError = "exchange-with-publish-error"
const exchangeWithPublishHangs = "exchange-with-publish-hangs"

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
}

func (ch *MockAmqpChannel) PublishWithDeferredConfirm(_ string, key string, _, _ bool, msg amqp.Publishing) (confirmation, error) {

	if key == exchangeWithPublishError {
		return nil, errors.New("publish error")
	}
	ch.msgs = append(ch.msgs, msg.Body)
	ch.headers = append(ch.headers, msg.Headers)

	done_ch := make(chan struct{}, 1)

	if key != exchangeWithPublishHangs {
		done_ch <- struct{}{}
	}

	ack := key != exchangeWithPublishNoAck
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
	if name == exchangeWithDeclareError {
		return errors.New("exchange declare error")
	}
	ch.exchangeName = name
	return nil
}

func (ch *MockAmqpChannel) QueueDeclare(name string, durable, _, _, _ bool, _ amqp.Table) (amqp.Queue, error) {
	if name == queueWithDeclareError {
		return amqp.Queue{}, errors.New("queue declare error")
	}
	ch.queueName = name
	ch.queueDurable = durable
	return amqp.Queue{}, nil
}

func (ch *MockAmqpChannel) QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return amqp.Queue{}, nil
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
	channelCalls     int
	amqpChannel      *MockAmqpChannel
	isclosed         bool
	errMode          bool
	confirmModeError bool
}

func (m *MockAmqpConnection) Channel() (amqpChannel, error) {
	if m.errMode {
		return nil, errors.New("failed to open channel")
	}
	m.channelCalls++
	m.amqpChannel = &MockAmqpChannel{
		confirmModeError: m.confirmModeError,
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
		arrange: create a queue with a fake amqp connection
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
		exchangeName: exchangeName,
	}

	headers := map[string]interface{}{"header1": "value1"}
	amqpProducer.Push(context.Background(), headers, []byte("TestMessage"))

	assert.Contains(t, mockAmqpChannel.headers, headers)
	assert.Contains(t, mockAmqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
}

func TestPushFailure(t *testing.T) {
	/*
		arrange: create a queue with a fake confirm handler that always fails
		act: push a message to the queue that will fail to publish
		assert: the push return an error
	*/
	tests := []struct {
		name      string
		queueName string
		context   context.Context
		errMsg    string
	}{
		{
			name:      "message is not acked",
			queueName: exchangeWithPublishNoAck,
			errMsg:    "confirmation not acknowledged",
			context:   context.Background(),
		},
		{
			name: "context is done",
			context: func() context.Context {
				ctx, cancel := context.WithCancel(context.Background())
				cancel()
				return ctx
			}(),
			queueName: exchangeWithPublishHangs,
			errMsg:    "context canceled",
		},
		{
			name:      "publish returns error",
			queueName: exchangeWithPublishError,
			errMsg:    "publish error",
			context:   context.Background(),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockAmqpChannel := &MockAmqpChannel{}
			amqpProducer := &AmqpProducer{
				client: &Client{
					amqpChannel: mockAmqpChannel,
					amqpConnection: &MockAmqpConnection{
						amqpChannel: mockAmqpChannel,
					},
				},
				exchangeName: tt.queueName,
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
	}

	err := amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
	assert.Error(t, err, "expected error when connection fails")
	assert.ErrorContains(t, err, "connection error")
}

func TestPushExchangeDeclare(t *testing.T) {
	/*
		arrange: create a producer with no amqp channel
		act: push a message to the queue
		assert: channel with confirm mode is established and exchange is declared
	*/
	mockAmqpConnection := &MockAmqpConnection{}
	amqpProducer := &AmqpProducer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		exchangeName: exchangeName,
	}

	amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))

	assert.Equal(t, mockAmqpConnection.amqpChannel.confirmMode, true, "expected channel to be in confirm mode")
	assert.Equal(t, mockAmqpConnection.amqpChannel.exchangeName, exchangeName, "expected exchange name to be "+exchangeName)
}

func TestPushExchangeDeclareFailure(t *testing.T) {
	/*
		arrange: create a queue with no amqp channel where the exchange declare fails
		act: push a message to the queue
		assert: push returns an error
	*/
	tests := []struct {
		name               string
		exchangeName       string
		mockAmqpConnection *MockAmqpConnection
		errMsg             string
	}{
		{
			name:               "exchange declare error",
			exchangeName:       exchangeWithDeclareError,
			mockAmqpConnection: &MockAmqpConnection{},
			errMsg:             "exchange declare error",
		},
		{
			name:         "confirm error",
			exchangeName: exchangeName,
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
				exchangeName: tt.exchangeName,
			}

			err := amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))

			assert.Error(t, err, "expected error when queue declare fails")
			assert.ErrorContains(t, err, tt.errMsg)
		})
	}
}
