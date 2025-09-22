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
const queueWithPublishNoAck = "queue-with-publish-no-ack"
const queueWithPublishError = "queue-with-publish-error"
const queueWithPublishHangs = "queue-with-publish-hangs"

type MockAmqpChannel struct {
	msgs         [][]byte
	headers      []map[string]interface{}
	isclosed     bool
	confirmMode  bool
	queueName    string
	queueDurable bool
}

func (ch *MockAmqpChannel) PublishWithDeferredConfirm(_ string, key string, _, _ bool, msg amqp.Publishing) (Confirmation, error) {

	if key == queueWithPublishError {
		return nil, errors.New("publish error")
	}
	ch.msgs = append(ch.msgs, msg.Body)
	ch.headers = append(ch.headers, msg.Headers)

	done_ch := make(chan struct{}, 1)

	if key != queueWithPublishHangs {
		done_ch <- struct{}{}
	}

	ack := key != queueWithPublishNoAck
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
	ch.confirmMode = true
	return nil
}

func (ch *MockAmqpChannel) QueueDeclare(name string, durable, _, _, _ bool, _ amqp.Table) (amqp.Queue, error) {
	ch.queueName = name
	ch.queueDurable = durable
	return amqp.Queue{}, nil
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
	channelCalls int
	amqpChannel  *MockAmqpChannel
	isclosed     bool
}

func (m *MockAmqpConnection) Channel() (AmqpChannel, error) {
	m.channelCalls++
	m.amqpChannel = &MockAmqpChannel{}
	return m.amqpChannel, nil
}

func (m *MockAmqpConnection) IsClosed() bool {
	return m.isclosed
}

func TestPush(t *testing.T) {
	/*
		arrange: create a queue with a fake amqp connection
		act: push a message to the queue
		assert: message was published to the amqp channel
	*/
	mockAmqpChannel := &MockAmqpChannel{}
	amqpProducer := &AmqpProducer{
		amqpChannel: mockAmqpChannel,
		amqpConnection: &MockAmqpConnection{
			amqpChannel: mockAmqpChannel,
		},
		queueName: queueName,
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
			queueName: queueWithPublishNoAck,
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
			queueName: queueWithPublishHangs,
			errMsg:    "context canceled",
		},
		{
			name:      "publish returns error",
			queueName: queueWithPublishError,
			errMsg:    "publish error",
			context:   context.Background(),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockAmqpChannel := &MockAmqpChannel{}
			amqpProducer := &AmqpProducer{
				amqpChannel: mockAmqpChannel,
				amqpConnection: &MockAmqpConnection{
					amqpChannel: mockAmqpChannel,
				},
				queueName: tt.queueName,
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
		channel AmqpChannel
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
				amqpChannel:    tt.channel,
				amqpConnection: mockAmqpConnection,
			}

			amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
			assert.Equal(t, 1, mockAmqpConnection.channelCalls, "expected connection to be re-established")
			assert.Contains(t, mockAmqpConnection.amqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
		})
	}
}

func TestPushNoConnection(t *testing.T) {
	/*
		arrange: create a queue with no amqp connection
		act: push a message to the queue
		assert: connection got established and message was published to the amqp channel
	*/
	tests := []struct {
		name       string
		connection AmqpConnection
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
			amqpConnection := &MockAmqpConnection{
				amqpChannel: &MockAmqpChannel{},
			}
			amqpProducer := &AmqpProducer{
				amqpConnection: tt.connection,
				uri:            "amqp://guest:guest@localhost:5672/",
				connectFunc: func(uri string) (AmqpConnection, error) {
					return amqpConnection, nil
				},
			}

			amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))
			assert.Equal(t, 1, amqpConnection.channelCalls, "expected connection to be re-established")
			assert.Contains(t, amqpConnection.amqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
		})
	}
}

func TestPushQueueDeclare(t *testing.T) {
	/*
		arrange: create a queue with no amqp channel
		act: push a message to the queue
		assert: channel with confirm mode is established and queue is declared
	*/
	mockAmqpConnection := &MockAmqpConnection{}
	queueName := "fakeQueue"
	amqpProducer := &AmqpProducer{
		amqpChannel:    nil,
		amqpConnection: mockAmqpConnection,
		queueName:      queueName,
	}

	amqpProducer.Push(context.Background(), nil, []byte("TestMessage"))

	assert.Equal(t, mockAmqpConnection.amqpChannel.confirmMode, true, "expected channel to be in confirm mode")
	assert.Equal(t, mockAmqpConnection.amqpChannel.queueName, queueName, "expected queue name to be "+queueName)
	assert.Equal(t, mockAmqpConnection.amqpChannel.queueDurable, true, "expected queue to be durable")
}
