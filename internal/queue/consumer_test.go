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

const queueName = "test-queue"

const queueWithDeclareError = "queue-with-declare-error"
const queueWithConsumeError = "queue-with-consume-error"
const queueWithQosError = "queue-with-qos-error"

type MockAmqpChannelConsumer struct {
	MockAmqpChannel
	msgChannel      chan amqp.Delivery
	qosCount        int
	qosSize         int
	qosGlobal       bool
	consumeCalls    int
	qosCalls        int
	consumerTag     string
	consumerAutoAck bool
}

func (ch *MockAmqpChannelConsumer) Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error) {
	if queue == queueWithConsumeError {
		return nil, errors.New("consume error")
	}
	ch.consumeCalls++
	ch.consumerTag = consumer
	ch.consumerAutoAck = autoAck
	if ch.msgChannel == nil {
		ch.msgChannel = make(chan amqp.Delivery, 1)
	}
	return ch.msgChannel, nil
}

func (ch *MockAmqpChannelConsumer) Qos(prefetchCount, prefetchSize int, global bool) error {
	if ch.queueName == queueWithQosError {
		return errors.New("qos error")
	}
	ch.qosCalls++
	ch.qosCount = prefetchCount
	ch.qosSize = prefetchSize
	ch.qosGlobal = global
	return nil
}

type MockAmqpConnectionConsumer struct {
	channelCalls         int
	amqpChannelConsumer  *MockAmqpChannelConsumer
	isclosed             bool
	errMode              bool
	confirmModeError     bool
	returnChannelOnSetup bool
}

func (m *MockAmqpConnectionConsumer) Channel() (amqpChannel, error) {
	if m.errMode {
		return nil, errors.New("failed to open channel")
	}
	m.channelCalls++
	if m.returnChannelOnSetup && m.amqpChannelConsumer != nil {
		return m.amqpChannelConsumer, nil
	}
	m.amqpChannelConsumer = &MockAmqpChannelConsumer{
		MockAmqpChannel: MockAmqpChannel{
			confirmModeError: m.confirmModeError,
		},
	}
	return m.amqpChannelConsumer, nil
}

func (m *MockAmqpConnectionConsumer) IsClosed() bool {
	return m.isclosed
}

func (m *MockAmqpConnectionConsumer) Close() error {
	m.isclosed = true
	return nil
}

func TestPull(t *testing.T) {
	/*
		arrange: create a consumer with a fake amqp connection and a message in the channel
		act: pull a message from the queue
		assert: message was received from the amqp channel
	*/
	msgChannel := make(chan amqp.Delivery, 1)
	expectedMsg := amqp.Delivery{
		Body: []byte("TestMessage"),
		Headers: amqp.Table{
			"header1": "value1",
		},
	}
	msgChannel <- expectedMsg

	mockAmqpChannel := &MockAmqpChannelConsumer{
		msgChannel: msgChannel,
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel: mockAmqpChannel,
			amqpConnection: &MockAmqpConnectionConsumer{
				amqpChannelConsumer: mockAmqpChannel,
			},
		},
		queueName: queueName,
		channel:   msgChannel,
	}

	msg, err := amqpConsumer.Pull(context.Background())

	assert.NoError(t, err)
	assert.Equal(t, expectedMsg.Body, msg.Body)
	assert.Equal(t, expectedMsg.Headers, msg.Headers)
}

func TestPullContextCanceled(t *testing.T) {
	/*
		arrange: create a consumer with a fake amqp connection and an empty message channel
		act: pull a message with a canceled context
		assert: pull returns context canceled error
	*/
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	msgChannel := make(chan amqp.Delivery)
	mockAmqpChannel := &MockAmqpChannelConsumer{
		msgChannel: msgChannel,
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel: mockAmqpChannel,
			amqpConnection: &MockAmqpConnectionConsumer{
				amqpChannelConsumer: mockAmqpChannel,
			},
		},
		queueName: queueName,
		channel:   msgChannel,
	}

	_, err := amqpConsumer.Pull(ctx)

	assert.Error(t, err)
	assert.ErrorIs(t, err, context.Canceled)
}

func TestPullChannelClosed(t *testing.T) {
	/*
		arrange: create a consumer with a fake amqp connection and a closed message channel
		act: pull a message from the queue
		assert: pull returns channel closed error
	*/
	msgChannel := make(chan amqp.Delivery)
	close(msgChannel)

	mockAmqpChannel := &MockAmqpChannelConsumer{
		msgChannel: msgChannel,
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel: mockAmqpChannel,
			amqpConnection: &MockAmqpConnectionConsumer{
				amqpChannelConsumer: mockAmqpChannel,
			},
		},
		queueName: queueName,
		channel:   msgChannel,
	}

	_, err := amqpConsumer.Pull(context.Background())

	assert.Error(t, err)
	assert.ErrorContains(t, err, "amqp message channel closed")
}

func TestPullNoChannel(t *testing.T) {
	/*
		arrange: create a consumer with no amqp channel
		act: pull a message from the queue
		assert: channel got established, Qos configured, and consume was called
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
			channel: &MockAmqpChannelConsumer{
				MockAmqpChannel: MockAmqpChannel{
					isclosed: true,
				},
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			msgChannel := make(chan amqp.Delivery, 1)
			msgChannel <- amqp.Delivery{Body: []byte("TestMessage")}

			mockAmqpChannelConsumer := &MockAmqpChannelConsumer{
				msgChannel: msgChannel,
			}
			mockAmqpConnection := &MockAmqpConnectionConsumer{
				amqpChannelConsumer:  mockAmqpChannelConsumer,
				returnChannelOnSetup: true,
			}
			amqpConsumer := &AmqpConsumer{
				client: &Client{
					amqpChannel:    tt.channel,
					amqpConnection: mockAmqpConnection,
				},
				queueName: queueName,
			}

			msg, err := amqpConsumer.Pull(context.Background())

			assert.NoError(t, err)
			assert.Equal(t, []byte("TestMessage"), msg.Body)
			assert.Equal(t, 1, mockAmqpConnection.channelCalls, "expected channel to be established")
			assert.Equal(t, 1, mockAmqpChannelConsumer.qosCalls, "expected Qos to be called once")
			assert.Equal(t, 1, mockAmqpChannelConsumer.qosCount, "expected prefetch count to be 1")
			assert.Equal(t, 1, mockAmqpChannelConsumer.consumeCalls, "expected Consume to be called once")
			assert.False(t, mockAmqpChannelConsumer.consumerAutoAck, "expected autoAck to be false")
		})
	}
}

func TestPullNoChannelFailure(t *testing.T) {
	/*
		arrange: create a consumer with no amqp channel where the channel function fails
		act: pull a message from the queue
		assert: pull returns an error
	*/
	mockAmqpConnection := &MockAmqpConnectionConsumer{
		errMode: true,
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		queueName: queueName,
	}

	_, err := amqpConsumer.Pull(context.Background())

	assert.Error(t, err, "expected error when channel fails to open")
	assert.ErrorContains(t, err, "failed to open channel")
}

func TestPullNoConnection(t *testing.T) {
	/*
		arrange: create a consumer with no amqp connection
		act: pull a message from the queue
		assert: connection got established and message was received
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
			connection: &MockAmqpConnectionConsumer{
				isclosed: true,
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			msgChannel := make(chan amqp.Delivery, 1)
			msgChannel <- amqp.Delivery{Body: []byte("TestMessage")}

			mockAmqpConnection := &MockAmqpConnectionConsumer{
				amqpChannelConsumer: &MockAmqpChannelConsumer{
					msgChannel: msgChannel,
				},
				returnChannelOnSetup: true,
			}
			amqpConsumer := &AmqpConsumer{
				client: &Client{
					amqpConnection: tt.connection,
					uri:            "amqp://guest:guest@localhost:5672/",
					connectFunc: func(uri string) (amqpConnection, error) {
						return mockAmqpConnection, nil
					},
				},
				queueName: queueName,
			}

			msg, err := amqpConsumer.Pull(context.Background())

			assert.NoError(t, err)
			assert.Equal(t, []byte("TestMessage"), msg.Body)
			assert.Equal(t, 1, mockAmqpConnection.channelCalls, "expected connection to be re-established")
		})
	}
}

func TestPullNoConnectionFailure(t *testing.T) {
	/*
		arrange: create a consumer with no amqp connection where the connect function fails
		act: pull a message from the queue
		assert: pull returns an error
	*/
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpConnection: nil,
			uri:            "amqp://guest:guest@localhost:5672/",
			connectFunc: func(uri string) (amqpConnection, error) {
				return nil, errors.New("connection error")
			},
		},
		queueName: queueName,
	}

	_, err := amqpConsumer.Pull(context.Background())

	assert.Error(t, err, "expected error when connection fails")
	assert.ErrorContains(t, err, "connection error")
}

func TestPullQueueDeclare(t *testing.T) {
	/*
		arrange: create a consumer with no amqp channel
		act: pull a message from the queue
		assert: channel is established and queue is declared
	*/
	msgChannel := make(chan amqp.Delivery, 1)
	msgChannel <- amqp.Delivery{Body: []byte("TestMessage")}

	mockAmqpChannelConsumer := &MockAmqpChannelConsumer{
		msgChannel: msgChannel,
	}
	mockAmqpConnection := &MockAmqpConnectionConsumer{
		amqpChannelConsumer:  mockAmqpChannelConsumer,
		returnChannelOnSetup: true,
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		queueName: queueName,
	}

	_, err := amqpConsumer.Pull(context.Background())

	assert.NoError(t, err)
	assert.True(t, mockAmqpChannelConsumer.confirmMode, "expected channel to be in confirm mode")
	assert.Equal(t, queueName, mockAmqpChannelConsumer.queueName, "expected queue name to be "+queueName)
	assert.True(t, mockAmqpChannelConsumer.queueDurable, "expected queue to be durable")
}

func TestPullQueueDeclareFailure(t *testing.T) {
	/*
		arrange: create a consumer with no amqp channel where the queue declare fails
		act: pull a message from the queue
		assert: pull returns an error
	*/
	tests := []struct {
		name               string
		queueName          string
		mockAmqpConnection *MockAmqpConnectionConsumer
		errMsg             string
	}{
		{
			name:               "queue declare error",
			queueName:          queueWithDeclareError,
			mockAmqpConnection: &MockAmqpConnectionConsumer{},
			errMsg:             "queue declare error",
		},
		{
			name:      "confirm error",
			queueName: queueName,
			mockAmqpConnection: &MockAmqpConnectionConsumer{
				confirmModeError: true,
			},
			errMsg: "confirm error",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			amqpConsumer := &AmqpConsumer{
				client: &Client{
					amqpChannel:    nil,
					amqpConnection: tt.mockAmqpConnection,
				},
				queueName: tt.queueName,
			}

			_, err := amqpConsumer.Pull(context.Background())

			assert.Error(t, err, "expected error when queue declare fails")
			assert.ErrorContains(t, err, tt.errMsg)
		})
	}
}

func TestPullQosFailure(t *testing.T) {
	/*
		arrange: create a consumer with no amqp channel where Qos fails
		act: pull a message from the queue
		assert: pull returns an error
	*/
	mockAmqpChannelConsumer := &MockAmqpChannelConsumer{
		MockAmqpChannel: MockAmqpChannel{
			queueName: queueWithQosError,
		},
	}
	mockAmqpConnection := &MockAmqpConnectionConsumer{
		amqpChannelConsumer:  mockAmqpChannelConsumer,
		returnChannelOnSetup: true,
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		queueName: queueWithQosError,
	}

	_, err := amqpConsumer.Pull(context.Background())

	assert.Error(t, err, "expected error when Qos fails")
	assert.ErrorContains(t, err, "qos error")
}

func TestPullConsumeFailure(t *testing.T) {
	/*
		arrange: create a consumer with no amqp channel where Consume fails
		act: pull a message from the queue
		assert: pull returns an error
	*/
	mockAmqpConnection := &MockAmqpConnectionConsumer{
		returnChannelOnSetup: true,
		amqpChannelConsumer:  &MockAmqpChannelConsumer{},
	}
	amqpConsumer := &AmqpConsumer{
		client: &Client{
			amqpChannel:    nil,
			amqpConnection: mockAmqpConnection,
		},
		queueName: queueWithConsumeError,
	}

	_, err := amqpConsumer.Pull(context.Background())

	assert.Error(t, err, "expected error when Consume fails")
	assert.ErrorContains(t, err, "consume error")
}

func TestNewAmqpConsumer(t *testing.T) {
	/*
		arrange: N/A
		act: create a new AmqpConsumer
		assert: consumer is properly initialized
	*/
	uri := "amqp://guest:guest@localhost:5672/"
	queueName := "test-queue"

	consumer := NewAmqpConsumer(uri, queueName)

	assert.NotNil(t, consumer)
	assert.Equal(t, queueName, consumer.queueName)
	assert.NotNil(t, consumer.client)
	assert.Equal(t, uri, consumer.client.uri)
	assert.NotNil(t, consumer.client.connectFunc)
}
