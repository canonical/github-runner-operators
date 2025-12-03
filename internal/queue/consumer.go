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
	client    *Client
	queueName string
	db        JobDatabase
	logger    *slog.Logger
}

// NewAmqpConsumer creates a new AmqpConsumer with the given dependencies.
func NewAmqpConsumer(uri, queueName string, db JobDatabase, logger *slog.Logger) *AmqpConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	return &AmqpConsumer{
		queueName: queueName,
		db:        db,
		logger:    logger,
		client: &Client{
			uri:         uri,
			connectFunc: amqpConnect,
		},
	}
}

// Start begins consuming messages from the AMQP queue and processing them.
func (c *AmqpConsumer) Start(ctx context.Context) error {
	err := c.resetConnectionOrChannelIfNecessary(ctx)
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
				c.logger.Warn("messages channel closed, retrying connection")
				if err := c.resetConnectionOrChannelIfNecessary(ctx); err != nil {
					return err
				}
				msgs, err = c.consumeMsgs()
				if err != nil {
					return err
				}
				continue
			}

			err := c.handleMessage(ctx, msg.Body)
			if err == nil {
				msg.Ack(false)
				continue
			}

			var errHandle *MessageHandlingError
			if errors.As(err, &errHandle) && !errHandle.Requeue {
				msg.Nack(false, false) // don't requeue
				c.logger.Error("failed to handle message without requeue", "error", err)
				continue
			}
			// Other errors are requeued by default
			c.logger.Error("failed to handle message, requeuing", "error", err)
			msg.Nack(false, true) // requeue
		}
	}
}

// resetConnectionOrChannelIfNecessary resets the AMQP connection or channel if they are nil or closed.
// It includes a retry mechanism with exponential backoff.
func (c *AmqpConsumer) resetConnectionOrChannelIfNecessary(ctx context.Context) error {
	backoff := time.Second
	maxBackoff := time.Minute

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		c.client.mu.Lock() // Lock to prevent concurrent access to connection/channel object

		err := c.client.resetConnection()
		if err == nil {
			err = c.client.resetChannel(c.queueName, true)
		}

		c.client.mu.Unlock()

		if err == nil {
			return nil
		}

		select {
		case <-time.After(backoff):
			if backoff < maxBackoff {
				backoff *= 2
			}
		case <-ctx.Done():
			return fmt.Errorf("retry canceled after error: %w", err)
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
	CreatedAt   string   `json:"created_at"`
	StartedAt   string   `json:"started_at,omitempty"`
	CompletedAt string   `json:"completed_at,omitempty"`
}

// handleMessage processes a single AMQP message body.
func (c *AmqpConsumer) handleMessage(ctx context.Context, body []byte) error {
	webhook := WorkflowJobWebhook{}
	if err := json.Unmarshal(body, &webhook); err != nil {
		return NoRetryableError(fmt.Sprintf("failed to unmarshal message body: %v", err))
	}
	switch webhook.Action {
	case "queued":
		return c.insertJobToDB(ctx, webhook.WorkflowJob, body)
	case "waiting":
		return nil
	case "in_progress":
		return c.updateJobStartedInDB(ctx, webhook.WorkflowJob, body)
	case "completed":
		return c.updateJobCompletedInDB(ctx, webhook.WorkflowJob, body)
	default:
		c.logger.Warn("ignoring other type", "status", webhook.Action)
		return NoRetryableError(fmt.Sprintf("ignoring webhook action type: %s", webhook.Action))
	}

}

// insertJobToDB inserts a new job into the database.
func (c *AmqpConsumer) insertJobToDB(ctx context.Context, j WorkflowJob, body []byte) error {
	createdAt := parseToTime(j.CreatedAt, c.logger)
	if createdAt == nil {
		return NoRetryableError("created_at missing in job_queued event")
	}

	job := &database.Job{
		ID:          strconv.Itoa(j.ID),
		Platform:    platform,
		Labels:      j.Labels,
		CreatedAt:   *createdAt,
		StartedAt:   parseToTime(j.StartedAt, c.logger),
		CompletedAt: parseToTime(j.CompletedAt, c.logger),
		Raw:         c.extractRaw(j.Status, body),
	}

	if err := c.db.AddJob(ctx, job); err != nil {
		if errors.Is(err, database.ErrExist) {
			c.logger.Info("job already exists in database", "job_id", j.ID)
			return NoRetryableError("job already exists in database")
		}
		return RetryableError(fmt.Sprintf("failed to add job to database: %v", err))
	}

	return nil
}

// updateJobStartedInDB updates the job's started_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *AmqpConsumer) updateJobStartedInDB(ctx context.Context, j WorkflowJob, body []byte) error {
	startedAt := parseToTime(j.StartedAt, c.logger)
	if startedAt == nil {
		return NoRetryableError("started_at missing in job_in_progress event")
	}

	if err := c.db.UpdateJobStarted(ctx, platform, strconv.Itoa(j.ID), *startedAt, c.extractRaw(j.Status, body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on start, inserting missing job", "job_id", j.ID)
			return c.insertJobToDB(ctx, j, body)
		}
		return RetryableError(fmt.Sprintf("failed to update job started in database: %v", err))
	}

	return nil
}

// updateJobCompletedInDB updates the job's completed_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *AmqpConsumer) updateJobCompletedInDB(ctx context.Context, j WorkflowJob, body []byte) error {
	completedAt := parseToTime(j.CompletedAt, c.logger)
	if completedAt == nil {
		return NoRetryableError("completed_at missing in job_completed event")
	}

	if err := c.db.UpdateJobCompleted(ctx, platform, strconv.Itoa(j.ID), *completedAt, c.extractRaw(j.Status, body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on completion, inserting missing job", "job_id", j.ID)
			return c.insertJobToDB(ctx, j, body)
		}
		return RetryableError(fmt.Sprintf("failed to update job completed in database: %v", err))
	}

	return nil
}

// extractRaw returns a map with the action type as the key and the
// stringified raw message body as the value.
func (c *AmqpConsumer) extractRaw(action string, body []byte) map[string]any {
	payload := map[string]any{
		action: string(body),
	}
	return payload
}

// consumeMsgs starts consuming messages from the AMQP queue.
func (c *AmqpConsumer) consumeMsgs() (<-chan amqp.Delivery, error) {
	err := c.client.amqpChannel.Qos(
		1,     // one message delivered at a time
		0,     // no specific size limit
		false, // apply to all consumers on this channel
	)
	if err != nil {
		return nil, fmt.Errorf("failed to set QoS: %w", err)
	}

	msgs, err := c.client.amqpChannel.Consume(
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
