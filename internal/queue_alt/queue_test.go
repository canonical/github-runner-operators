/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue_alt

import (
	"testing"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

type MockAmqpChannel struct {
	msgs     [][]byte
	headers  []map[string]interface{}
	isclosed bool
}

func (ch *MockAmqpChannel) PublishWithDeferredConfirm(_ string, _ string, _, _ bool, msg amqp.Publishing) (*interface{}, error) {

	ch.msgs = append(ch.msgs, msg.Body)
	ch.headers = append(ch.headers, msg.Headers)
	return nil, nil
}

func (ch *MockAmqpChannel) IsClosed() bool {
	return ch.isclosed
}

type MockAmqpConnection struct {
	channelCalls int
	amqpChannel  *MockAmqpChannel
}

func (m *MockAmqpConnection) Channel() (AmqpChannel, error) {
	m.channelCalls++
	m.amqpChannel = &MockAmqpChannel{}
	return m.amqpChannel, nil
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
	}

	headers := map[string]interface{}{"header1": "value1"}
	amqpProducer.Push(nil, headers, []byte("TestMessage"))

	assert.Contains(t, mockAmqpChannel.headers, headers)
	assert.Contains(t, mockAmqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
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

			amqpProducer.Push(nil, nil, []byte("TestMessage"))
			assert.Equal(t, 1, mockAmqpConnection.channelCalls, "expected connection to be re-established")
			assert.Contains(t, mockAmqpConnection.amqpChannel.msgs, []byte("TestMessage"), "expected message to be published")
		})
	}

}
