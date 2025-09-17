/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

const QueueWithDeclareError = "queue-with-declare-error"
const TestMessage = "TestMessage"

type MockAmqpChannel struct {
	queueName         string
	publishedMessages [][]byte
	closed            bool
	confirmMode       bool
	errorChan         chan *amqp.Error
	mutex             sync.Mutex
}

type MockAmqConnection struct {
	channel *MockAmqpChannel
	closed  bool
	mutex   sync.Mutex
}

func (ch *MockAmqpChannel) PublishWithDeferredConfirm(_ string, _ string, _, _ bool, msg amqp.Publishing) (*amqp.DeferredConfirmation, error) {
	ch.publishedMessages = append(ch.publishedMessages, msg.Body)
	return nil, nil
}

func (ch *MockAmqpChannel) QueueDeclare(name string, _, _, _, _ bool, _ amqp.Table) (amqp.Queue, error) {
	if name == QueueWithDeclareError {
		return amqp.Queue{}, errors.New("failed to declare queue")
	}
	ch.queueName = name
	return amqp.Queue{}, nil
}

func (ch *MockAmqpChannel) Close() error {
	ch.mutex.Lock()
	defer ch.mutex.Unlock()
	ch.closed = true
	return nil
}

func (ch *MockAmqpChannel) NotifyClose(c chan *amqp.Error) chan *amqp.Error {
	ch.mutex.Lock()
	defer ch.mutex.Unlock()
	ch.errorChan = c
	return c
}

func (ch *MockAmqpChannel) Confirm(_ bool) error {
	ch.confirmMode = true
	return nil
}

func (c *MockAmqConnection) Channel() (AmqpChannel, error) {
	if c.channel == nil {
		c.channel = &MockAmqpChannel{}
	}
	return c.channel, nil
}

func (c *MockAmqConnection) Close() error {
	c.mutex.Lock()
	defer c.mutex.Unlock()
	c.closed = true
	return nil
}

func mockConfirmHandlerSuccess(confirmationChan chan bool, _ *amqp.DeferredConfirmation) {
	go func() {
		// Simulate a successful confirmation
		confirmationChan <- true
	}()
}

func mockConfirmHandlerFailure(confirmationChan chan bool, _ *amqp.DeferredConfirmation) {
	go func() {
		// Simulate a failed confirmation
		confirmationChan <- false
	}()
}

func TestPushWithSuccess(t *testing.T) {
	/*
		arrange: create a producer that always confirms
		act: push a message to the queue
		assert: no error is returned
	*/
	producerChan := make(chan ProduceMsg, 1)
	fakeProducer := createProducer(producerChan)
	go func() {
		produceMsg := <-producerChan
		produceMsg.confirmationChan <- true
	}()

	err := fakeProducer.Push(context.Background(), []byte(TestMessage))

	assert.NoError(t, err)
}

func createProducer(producerChan chan ProduceMsg) AmqpProducer {
	return AmqpProducer{
		queue: &AmqpQueue{
			URI:  "amqp://guest:guest@localhost:5672/",
			Name: "test-queue",
		},
		producerChan: producerChan,
	}
}

func TestPushWithFailure(t *testing.T) {
	/*
		arrange: create a producer that always fails to confirm
		act: push a message to the queue
		assert: an error is returned
	*/
	producerChan := make(chan ProduceMsg, 1)
	fakeProducer := createProducer(producerChan)
	go func() {
		produceMsg := <-producerChan
		produceMsg.confirmationChan <- false
	}()

	err := fakeProducer.Push(context.Background(), []byte("TestMessage"))

	assert.Error(t, err)
	assert.ErrorContains(t, err, "message not confirmed")
}

func TestPushContextCancelled(t *testing.T) {
	/*
		arrange: create a producer that never confirms and a context that will be cancelled
		act: push a message to the queue
		assert: an error is returned after timeout
	*/
	producerChan := make(chan ProduceMsg, 1)
	fakeProducer := createProducer(producerChan)
	go func() {
		<-producerChan
	}()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := fakeProducer.Push(ctx, []byte("TestMessage"))
	assert.Error(t, err)
	assert.ErrorContains(t, err, "context canceled")
}

func TestProducerSetupsChannelAndQueue(t *testing.T) {
	/*
		arrange: create a fake AmqpQueue and a mock connection function
		act: start the producer
		assert: the channel is in confirm mode and the queue name matches
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := createProducer(producerChan)
	_, fakeAmqpChan, connectFunc := createConnectFunc()
	shutdownChan <- true

	err := producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerSuccess)

	assert.NoError(t, err)
	assert.True(t, fakeAmqpChan.confirmMode, "channel should be in confirm mode")
	assert.Equal(t, "test-queue", fakeAmqpChan.queueName, "queue name should match")

}

func createConnectFunc() (*MockAmqConnection, *MockAmqpChannel, func(uri string) (AmqpConnection, error)) {
	fakeAmqpChan := MockAmqpChannel{}
	fakeAmqpConn := MockAmqConnection{
		channel: &fakeAmqpChan,
		closed:  false,
	}
	connectFunc := func(uri string) (AmqpConnection, error) {
		return &fakeAmqpConn, nil
	}
	return &fakeAmqpConn, &fakeAmqpChan, connectFunc
}

func TestProducerPublishesMessage(t *testing.T) {
	/*
		arrange: mock the confirm handler to always confirm
		act: start the producer and send a message to the producer channel
		assert: the message is published and confirmed
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := createProducer(producerChan)
	_, fakeAmqpChan, connectFunc := createConnectFunc()
	confirmationChan := make(chan bool, 1)

	go producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerSuccess)
	produceMsg := ProduceMsg{
		msg:              []byte(TestMessage),
		confirmationChan: confirmationChan,
	}
	producerChan <- produceMsg

	assert.True(t, <-confirmationChan, "message should be confirmed")
	assert.Contains(t, fakeAmqpChan.publishedMessages, []byte(TestMessage), "published messages should contain the test message")
	shutdownChan <- true
}

func TestProducerCouldNotPublishMessage(t *testing.T) {
	/*
		arrange: mock the confirm handler to always fail
		act: start the producer and send a message to the producer channel
		assert: the message is not confirmed
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := createProducer(producerChan)
	_, _, connectFunc := createConnectFunc()
	confirmationChan := make(chan bool, 1)
	produceMsg := ProduceMsg{
		msg:              []byte(TestMessage),
		confirmationChan: confirmationChan,
	}
	producerChan <- produceMsg

	go producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerFailure)

	assert.False(t, <-confirmationChan, "message should not be confirmed")
	shutdownChan <- true
}

func TestProducerChannelShutDownTriesReconnect(t *testing.T) {
	/*
		arrange: create a mock connection function that counts calls
		act: start the producer and simulate a channel error
		assert: the connect function is called multiple times
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := createProducer(producerChan)
	fakeAmqpChan := MockAmqpChannel{}
	fakeAmqpConn := MockAmqConnection{
		channel: &fakeAmqpChan,
		closed:  false,
	}
	mutex := sync.Mutex{}
	connectCalls := 0
	connectFunc := func(uri string) (AmqpConnection, error) {
		mutex.Lock()
		defer mutex.Unlock()
		connectCalls++
		return &fakeAmqpConn, nil
	}

	go producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerSuccess)
	assert.Eventually(t, func() bool {
		fakeAmqpChan.mutex.Lock()
		defer fakeAmqpChan.mutex.Unlock()
		return fakeAmqpChan.errorChan != nil
	}, time.Second, 1, "error channel should be set")
	fakeAmqpChan.errorChan <- amqp.ErrClosed

	assert.Eventually(t, func() bool {
		mutex.Lock()
		defer mutex.Unlock()
		return connectCalls >= 2
	}, time.Second, 1, "connect should be called multiple times")
	shutdownChan <- true
}

func TestProducerConnectError(t *testing.T) {
	/*
		arrange: create a mock connection function that always fails
		act: start the producer
		assert: an error is returned
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := createProducer(producerChan)
	connectFunc := func(uri string) (AmqpConnection, error) {
		return nil, errors.New("error")
	}

	err := producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerSuccess)

	assert.Error(t, err)
	assert.ErrorContains(t, err, "failed to connect to RabbitMQ")
}

func TestProducerQueueDeclareError(t *testing.T) {
	/*
		arrange: create a fake AmqpQueue that will fail to declare the queue
		act: start the producer
		assert: an error is returned
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := AmqpProducer{queue: &AmqpQueue{
		URI:  "amqp://guest:guest@localhost:5672/",
		Name: QueueWithDeclareError,
	},
		producerChan: producerChan,
	}
	_, _, connectFunc := createConnectFunc()

	err := producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerSuccess)

	assert.Error(t, err)
	assert.ErrorContains(t, err, "failed to declare a queue")
}

func TestProducerClosesResources(t *testing.T) {
	/*
		arrange: start the producer
		act: send a shutdown signal
		assert: the connection and channel are closed
	*/
	producerChan := make(chan ProduceMsg, 1)
	shutdownChan := make(chan bool, 1)
	fakeProducer := createProducer(producerChan)
	fakeAmqpConn, fakeAmqpChan, connectFunc := createConnectFunc()
	go producer(&fakeProducer, shutdownChan, connectFunc, mockConfirmHandlerSuccess)

	shutdownChan <- true

	assert.Eventually(t,
		func() bool {
			fakeAmqpConn.mutex.Lock()
			defer fakeAmqpConn.mutex.Unlock()
			return fakeAmqpConn.closed
		}, time.Second, 1, "connection should be closed")

	assert.Eventually(t,
		func() bool {
			fakeAmqpChan.mutex.Lock()
			defer fakeAmqpChan.mutex.Unlock()
			return fakeAmqpChan.closed
		}, time.Second, 1, "channel should should be closed")

}
