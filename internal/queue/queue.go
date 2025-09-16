/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package queue

import (
	"context"
	"errors"
	"log"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

type Queue interface {
	Push([]byte) error
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
	URI          string
	Name         string
	ProducerChan chan ProduceMsg
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

func NewAmqpQueue(uri, name string) *AmqpQueue {
	return &AmqpQueue{
		URI:          uri,
		Name:         name,
		ProducerChan: make(chan ProduceMsg),
	}
}

func (q *AmqpQueue) StartProducer() {
	go func() {

		err := Producer(q, q.ProducerChan, make(chan bool), connect, confirmHandler)
		if err != nil {
			log.Panicf("Producer error: %s", err)
		}
	}()
}

func connect(uri string) (AmqpConnection, error) {
	conn, err := amqp.Dial(uri)
	if err != nil {
		return nil, errors.New("Failed to connect to RabbitMQ." + err.Error())
	}

	return &AmpqConnectionWrapper{conn: conn}, nil
}

func setupChannel(amqpConnection AmqpConnection, queueName string) (AmqpChannel, chan *amqp.Error, error) {
	amqpChannel, err := amqpConnection.Channel()
	if err != nil {
		return nil, nil, errors.New("Failed to open a channel: " + err.Error())
	}

	errChan := make(chan *amqp.Error, 1)
	amqpChannel.NotifyClose(errChan)

	err = amqpChannel.Confirm(false)
	if err != nil {
		return nil, nil, errors.New("Failed to put channel into confirm mode: " + err.Error())
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
		return nil, nil, errors.New("Failed to declare a queue: " + err.Error())
	}

	return amqpChannel, errChan, nil
}

func Producer(q *AmqpQueue, producerChan chan ProduceMsg, shutdownChan chan bool, connectFunc ConnectFunc, confirmHandlerFunc ConfirmHandler) error {

	amqpConnection, err := connectFunc(q.URI)

	if err != nil {
		return errors.New("Failed to connect to RabbitMQ: " + err.Error())
	}

	defer func() {
		err := amqpConnection.Close()
		if err != nil {
			log.Println("Failed to close AMQP connection:", err)
		}
	}()

	amqpChannel, connErrorChan, err := setupChannel(amqpConnection, q.Name)
	if err != nil {
		return errors.New("Failed to setup channel: " + err.Error())
	}

	defer func() {
		err := amqpChannel.Close()
		if err != nil {
			log.Println("Failed to close AMQP channel:", err)
		}
	}()

	for {

		var produceMsg ProduceMsg
		select {

		case produceMsg = <-producerChan:
		case _ = <-shutdownChan:
			return nil
		case err := <-connErrorChan:
			log.Println("Connection error:", err)
			var connectErr error
			amqpConnection, connectErr = connectFunc(q.URI)

			if connectErr != nil {
				return errors.New("Failed to reconnect to RabbitMQ: " + connectErr.Error())
			}
			var channelSetupErr error
			amqpChannel, connErrorChan, channelSetupErr = setupChannel(amqpConnection, q.Name)
			if channelSetupErr != nil {
				return errors.New("Failed to setup channel: " + channelSetupErr.Error())
			}
		}

		deferredConfirm, err := amqpChannel.PublishWithDeferredConfirm(
			"",     // exchange
			q.Name, // routing key
			false,  // mandatory
			false,  // immediate
			amqp.Publishing{
				ContentType: "application/json",
				Body:        produceMsg.msg,
			},
		)
		if err != nil {
			// if publish fails, we should notify the caller that the message was not confirmed
			produceMsg.confirmationChan <- false
			log.Println("Failed to publish message:", err)
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

func (q *AmqpQueue) Push(msg []byte) error {
	confirmationChan := make(chan bool)
	channelMsg := ProduceMsg{
		msg:              msg,
		confirmationChan: confirmationChan,
	}

	q.ProducerChan <- channelMsg

	confirmation := <-confirmationChan

	if confirmation != true {
		return errors.New("message not confirmed")
	}
	return nil
}
