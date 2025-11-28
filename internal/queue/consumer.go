/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package queue provides AMQP consumer implementations for job events.
 *
 */

package queue

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	amqp "github.com/rabbitmq/amqp091-go"
)

const platform = "github"

// JobDatabase is a small interface that matches the relevant method on internal/database.Database.
type JobDatabase interface {
	AddJob(ctx context.Context, job *database.Job) error
	UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]any) error
	UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]any) error
}

// AmqpConsumer is an AMQP consumer for workflow job events.
type AmqpConsumer struct {
	amqpChannel    amqpChannel
	amqpConnection amqpConnection
	connectFunc    func(uri string) (amqpConnection, error)
	uri            string
	queueName      string
	db             JobDatabase
	mu             sync.Mutex
	logger         *slog.Logger
}

// NewAmqpConsumer creates a new AmqpConsumer with the given dependencies.
func NewAmqpConsumer(uri, queueName string, db JobDatabase, logger *slog.Logger) *AmqpConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	return &AmqpConsumer{
		uri:         uri,
		queueName:   queueName,
		connectFunc: amqpConnect,
		db:          db,
		logger:      logger,
	}
}

// Start begins consuming messages from the AMQP queue and processing them.
func (c *AmqpConsumer) Start(ctx context.Context) error {
	err := c.resetConnectionOrChannelIfNecessary()
	if err != nil {
		return err
	}

	msgs, err := c.consumeMsgs()
	if err != nil {
		return err
	}

	c.logger.Info("AMQP consumer started", "queue", c.queueName)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case msg, ok := <-msgs:
			if !ok {
				return fmt.Errorf("messages channel closed")
			}
			if err := c.handleMessage(ctx, msg); err != nil {
				c.logger.Error("failed to handle message", "error", err)
			}
		}
	}
}

// WorkflowJobWebhook represents the structure of a workflow job webhook message.
type WorkflowJobWebhook struct {
	Action      string      `json:"action"`
	WorkflowJob WorkflowJob `json:"workflow_job"`
}

// WorkflowJob represents the structure of a workflow job in the webhook message.
type WorkflowJob struct {
	ID          int      `json:"id"`
	Labels      []string `json:"labels"`
	Status      string   `json:"status"`
	CreatedAt   *string  `json:"created_at"`
	StartedAt   *string  `json:"started_at,omitempty"`
	CompletedAt *string  `json:"completed_at,omitempty"`
}

// handleMessage processes a single AMQP message.
func (c *AmqpConsumer) handleMessage(ctx context.Context, msg amqp.Delivery) error {
	webhook := WorkflowJobWebhook{}
	if err := json.Unmarshal(msg.Body, &webhook); err != nil {
		msg.Nack(false, false) // don't requeue
		return fmt.Errorf("failed to unmarshal message body: %w", err)
	}
	switch webhook.Action {
	case "queued":
		return c.insertJobToDB(ctx, webhook.WorkflowJob, msg)
	case "waiting":
		msg.Ack(false) // already handled in "queued"
		return nil
	case "in_progress":
		return c.updateJobStartedInDB(ctx, webhook.WorkflowJob, msg)
	case "completed":
		return c.updateJobCompletedInDB(ctx, webhook.WorkflowJob, msg)
	default:
		c.logger.Warn("ignoring other type", "status", webhook.Action)
		msg.Nack(false, false) // don't requeue
		return nil
	}
}

// insertJobToDB inserts a new job into the database.
func (c *AmqpConsumer) insertJobToDB(ctx context.Context, j WorkflowJob, msg amqp.Delivery) error {
	job := &database.Job{
		ID:          strconv.Itoa(j.ID),
		Platform:    platform,
		Labels:      j.Labels,
		CreatedAt:   parseToTime(j.CreatedAt, c.logger),
		StartedAt:   nil,
		CompletedAt: nil,
		Raw:         c.extractRaw(msg.Body),
	}
	if err := c.db.AddJob(ctx, job); err != nil {
		if errors.Is(err, database.ErrExist) {
			c.logger.Info("job already exists in database", "job_id", j.ID)
			msg.Nack(false, false) // don't requeue
			return nil
		}
		msg.Nack(false, true) // requeue
		return fmt.Errorf("failed to add job to database: %w", err)
	}
	msg.Ack(false)
	return nil
}

// updateJobStartedInDB updates the job's started_at timestamp in the database.
func (c *AmqpConsumer) updateJobStartedInDB(ctx context.Context, j WorkflowJob, msg amqp.Delivery) error {
	if parseToTime(j.StartedAt, c.logger).IsZero() {
		msg.Nack(false, false) // don't requeue
		return errors.New("started_at missing in job_started event")
	}
	if err := c.db.UpdateJobStarted(ctx, platform, strconv.Itoa(j.ID), parseToTime(j.StartedAt, c.logger), c.extractRaw(msg.Body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on start", "job_id", j.ID)
			msg.Nack(false, false) // don't requeue
			return nil
		}
		msg.Nack(false, true) // requeue
		return fmt.Errorf("failed to update job started in database: %w", err)
	}
	msg.Ack(false)
	return nil
}

// updateJobCompletedInDB updates the job's completed_at timestamp in the database.
func (c *AmqpConsumer) updateJobCompletedInDB(ctx context.Context, j WorkflowJob, msg amqp.Delivery) error {
	if parseToTime(j.CompletedAt, c.logger).IsZero() {
		msg.Nack(false, false) // don't requeue
		return errors.New("completed_at missing in job_completed event")
	}
	if err := c.db.UpdateJobCompleted(ctx, platform, strconv.Itoa(j.ID), parseToTime(j.CompletedAt, c.logger), c.extractRaw(msg.Body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on completion", "job_id", j.ID)
			msg.Nack(false, false) // don't requeue
			return nil
		}
		msg.Nack(false, true) // requeue
		return fmt.Errorf("failed to update job completed in database: %w", err)
	}
	msg.Ack(false)
	return nil
}

// extractRaw extracts the raw payload from the AMQP message body.
func (c *AmqpConsumer) extractRaw(body []byte) map[string]any {
	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		c.logger.Warn("failed to extract raw payload", "error", err)
		return nil
	}
	return payload
}

// consumeMsgs starts consuming messages from the AMQP queue.
func (c *AmqpConsumer) consumeMsgs() (<-chan amqp.Delivery, error) {
	err := c.amqpChannel.Qos(
		1,     // one message delivered at a time
		0,     // no specific size limit
		false, // apply to all consumers on this channel
	)
	if err != nil {
		return nil, fmt.Errorf("failed to set QoS: %w", err)
	}

	msgs, err := c.amqpChannel.Consume(
		c.queueName, // queue
		"",          // consumer tag, empty string means a unique random tag will be generated
		false,       // whether rabbitmq auto-acknowledges messages
		true,        // whether only this consumer can access the queue
		false,       // no-local
		false,       // false means wait for server confirmation that consumer is registered
		nil,         // args
	)
	if err != nil {
		return nil, fmt.Errorf("failed to consume message: %w", err)
	}
	return msgs, nil
}

// resetConnectionOrChannelIfNecessary resets the AMQP connection or channel if they are nil or closed.
func (c *AmqpConsumer) resetConnectionOrChannelIfNecessary() error {
	c.mu.Lock() // Lock to prevent concurrent access to connection/channel object
	defer c.mu.Unlock()

	if c.amqpConnection == nil || c.amqpConnection.IsClosed() {
		err := c.resetConnection()
		if err != nil {
			return err
		}
	}

	if c.amqpChannel == nil || c.amqpChannel.IsClosed() {
		err := c.resetChannel()
		if err != nil {
			return err
		}
	}

	return nil
}

// resetConnection establishes a new AMQP connection.
func (c *AmqpConsumer) resetConnection() error {
	conn, err := c.connectFunc(c.uri)
	if err != nil {
		return fmt.Errorf("failed to connect to AMQP server: %w", err)
	}
	c.amqpConnection = conn
	return nil
}

// resetChannel opens a new AMQP channel and declares the queue.
func (c *AmqpConsumer) resetChannel() error {
	ch, err := c.amqpConnection.Channel()
	if err != nil {
		return fmt.Errorf("failed to open AMQP channel: %w", err)
	}
	c.amqpChannel = ch

	err = ch.Confirm(false)
	if err != nil {
		return fmt.Errorf("failed to put channel in confirm mode: %w", err)
	}

	_, err = ch.QueueDeclarePassive(
		c.queueName, // queueName
		true,        // durable
		false,       // delete when unused
		false,       // exclusive
		false,       // no-wait
		nil,         // arguments
	)
	if err != nil {
		return fmt.Errorf("failed to declare AMQP queue: %w", err)
	}

	return nil
}
