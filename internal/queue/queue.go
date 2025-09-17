/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"fmt"
	"log"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

type Producer interface {
	Push(context.Context, []byte) error
}

type AmqpChannel interface {
	QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error)
	PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (*amqp.DeferredConfirmation, error)
	NotifyClose(chan *amqp.Error) chan *amqp.Error
	Confirm(noWait bool) error
	Close() error
}

type AmqpConnection interface {
	Channel() (AmqpChannel, error)
	Close() error
}

type ConfirmHandler func(confirmationChan chan bool, deferredConfirmation *amqp.DeferredConfirmation)
type ConnectFunc func(uri string) (AmqpConnection, error)

type ProduceMsg struct {
	msg              []byte
	confirmationChan chan bool
}
type AmqpQueue struct {
	// Add fields for AMQP connection, channel, etc.
	URI  string
	Name string
}

type AmqpProducer struct {
	queue        *AmqpQueue
	producerChan chan ProduceMsg
}

type AmpqConnectionWrapper struct {
	conn *amqp.Connection
}

func (q *AmpqConnectionWrapper) Channel() (AmqpChannel, error) {
	return q.conn.Channel()
}

func (q *AmpqConnectionWrapper) Close() error {
	return q.conn.Close()
}

func NewProducer(uri, name string) *AmqpProducer {
	q := &AmqpQueue{
		URI:  uri,
		Name: name,
	}
	p := &AmqpProducer{
		queue:        q,
		producerChan: make(chan ProduceMsg),
	}
	go func() {

		err := producer(p, make(chan bool), connect, confirmHandler)
		if err != nil {
			log.Panicf("Producer error: %s", err)
		}
	}()
	return p
}

func (p *AmqpProducer) Push(ctx context.Context, msg []byte) error {
	confirmationChan := make(chan bool)
	channelMsg := ProduceMsg{
		msg:              msg,
		confirmationChan: confirmationChan,
	}

	p.producerChan <- channelMsg

	select {
	case <-ctx.Done():
		return ctx.Err()

	case confirmation := <-confirmationChan:
		if confirmation != true {
			return fmt.Errorf("message not confirmed")
		}
	}
	return nil
}

func connect(uri string) (AmqpConnection, error) {
	conn, err := amqp.Dial(uri)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to RabbitMQ: %w", err)
	}

	return &AmpqConnectionWrapper{conn: conn}, nil
}

func setupChannel(amqpConnection AmqpConnection, queueName string) (AmqpChannel, chan *amqp.Error, error) {
	amqpChannel, err := amqpConnection.Channel()
	if err != nil {
		return nil, nil, fmt.Errorf("failed to open a channel: %w", err)
	}

	errChan := make(chan *amqp.Error, 1)
	amqpChannel.NotifyClose(errChan)

	err = amqpChannel.Confirm(false)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to put channel into confirm mode: %w", err)
	}

	_, err = amqpChannel.QueueDeclare(
		queueName, // name
		true,      // durable
		false,     // delete when unused
		false,     // exclusive
		false,     // no-wait
		nil,       // arguments
	)
	if err != nil {
		return nil, nil, fmt.Errorf("failed to declare a queue: %w", err)
	}

	return amqpChannel, errChan, nil
}

func producer(p *AmqpProducer, shutdownChan chan bool, connectFunc ConnectFunc, confirmHandlerFunc ConfirmHandler) error {

	amqpConnection, err := connectFunc(p.queue.URI)

	if err != nil {
		return fmt.Errorf("failed to connect to RabbitMQ: %w", err)
	}

	defer func() {
		err := amqpConnection.Close()
		if err != nil {
			log.Println("failed to close AMQP connection", err)
		}
	}()

	amqpChannel, connErrorChan, err := setupChannel(amqpConnection, p.queue.Name)
	if err != nil {
		return fmt.Errorf("failed to setup channel: %w", err)
	}

	defer func() {
		err := amqpChannel.Close()
		if err != nil {
			log.Println("failed to close AMQP channel", err)
		}
	}()

	for {

		var produceMsg ProduceMsg
		select {

		case produceMsg = <-p.producerChan:
		case _ = <-shutdownChan:
			return nil
		case err := <-connErrorChan:
			log.Println("Connection error:", err)
			var connectErr error
			amqpConnection, connectErr = connectFunc(p.queue.URI)

			if connectErr != nil {
				return fmt.Errorf("failed to reconnect to RabbitMQ: %w", connectErr)
			}
			var channelSetupErr error
			amqpChannel, connErrorChan, channelSetupErr = setupChannel(amqpConnection, p.queue.Name)
			if channelSetupErr != nil {
				return fmt.Errorf("failed to setup channel: %w", channelSetupErr)
			}
		}

		deferredConfirm, err := amqpChannel.PublishWithDeferredConfirm(
			"",           // exchange
			p.queue.Name, // routing key
			false,        // mandatory
			false,        // immediate
			amqp.Publishing{
				ContentType: "application/json",
				Body:        produceMsg.msg,
			},
		)
		if err != nil {
			// if publish fails, we should notify the caller that the message was not confirmed
			produceMsg.confirmationChan <- false
			log.Println("failed to publish message:", err)
			continue // skip to next message
		}
		log.Println("Waiting for confirmation...", deferredConfirm)

		go confirmHandlerFunc(produceMsg.confirmationChan, deferredConfirm)
	}

}

func confirmHandler(confirmationChan chan bool, deferredConfirmation *amqp.DeferredConfirmation) {
	timeout, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	log.Println("Waiting for confirmation...", deferredConfirmation)
	confirmation, _ := deferredConfirmation.WaitContext(timeout)
	log.Println("Confirmation received:", confirmation)
	confirmationChan <- confirmation
}
