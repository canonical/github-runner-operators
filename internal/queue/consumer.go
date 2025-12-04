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

			if errors.Is(err, ErrNonRetryable) {
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
		return classifyError(fmt.Errorf("%w: %v", ErrInvalidJSON, err))
	}

	var err error
	switch webhook.Action {
	case "queued":
		err = c.insertJobToDB(ctx, webhook.WorkflowJob, body)
	case "waiting":
		return nil
	case "in_progress":
		err = c.updateJobStartedInDB(ctx, webhook.WorkflowJob, body)
	case "completed":
		err = c.updateJobCompletedInDB(ctx, webhook.WorkflowJob, body)
	default:
		c.logger.Warn("ignoring other type", "status", webhook.Action)
		return classifyError(fmt.Errorf("%w: %s", ErrUnknownAction, webhook.Action))
	}

	// Classify the error to determine if it should be retried
	if err != nil {
		return classifyError(err)
	}
	return nil
}

// insertJobToDB inserts a new job into the database.
func (c *AmqpConsumer) insertJobToDB(ctx context.Context, j WorkflowJob, body []byte) error {
	if j.CreatedAt == "" || j.CreatedAt == "null" {
		return fmt.Errorf("%w: created_at in job_queued event", ErrMissingField)
	}
	createdAt, err := time.Parse(time.RFC3339, j.CreatedAt)
	if err != nil {
		return fmt.Errorf("%w: failed to parse created_at: %v", ErrInvalidTimestamp, err)
	}

	job := &database.Job{
		ID:          strconv.Itoa(j.ID),
		Platform:    platform,
		Labels:      j.Labels,
		CreatedAt:   createdAt,
		StartedAt:   c.parseOptionalTime(j.StartedAt),
		CompletedAt: c.parseOptionalTime(j.CompletedAt),
		Raw:         c.extractRaw(j.Status, body),
	}

	if err := c.db.AddJob(ctx, job); err != nil {
		if errors.Is(err, database.ErrExist) {
			c.logger.Info("job already exists in database", "job_id", j.ID)
			return fmt.Errorf("%w: job %d", ErrJobAlreadyExists, j.ID)
		}
		return fmt.Errorf("failed to add job to database: %w", err)
	}

	return nil
}

// parseOptionalTime parses an optional time string, returning nil if empty or invalid.
func (c *AmqpConsumer) parseOptionalTime(timeStr string) *time.Time {
	if timeStr == "" || timeStr == "null" {
		return nil
	}
	t, err := time.Parse(time.RFC3339, timeStr)
	if err != nil {
		c.logger.Warn("failed to parse time", "timeStr", timeStr, "error", err)
		return nil
	}
	return &t
}

// updateJobStartedInDB updates the job's started_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *AmqpConsumer) updateJobStartedInDB(ctx context.Context, j WorkflowJob, body []byte) error {
	if j.StartedAt == "" || j.StartedAt == "null" {
		return fmt.Errorf("%w: started_at in job_in_progress event", ErrMissingField)
	}
	startedAt, err := time.Parse(time.RFC3339, j.StartedAt)
	if err != nil {
		return fmt.Errorf("%w: failed to parse started_at: %v", ErrInvalidTimestamp, err)
	}

	if err := c.db.UpdateJobStarted(ctx, platform, strconv.Itoa(j.ID), startedAt, c.extractRaw(j.Status, body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on start, inserting missing job", "job_id", j.ID)
			return c.insertJobToDB(ctx, j, body)
		}
		return fmt.Errorf("failed to update job started in database: %w", err)
	}

	return nil
}

// updateJobCompletedInDB updates the job's completed_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *AmqpConsumer) updateJobCompletedInDB(ctx context.Context, j WorkflowJob, body []byte) error {
	if j.CompletedAt == "" || j.CompletedAt == "null" {
		return fmt.Errorf("%w: completed_at in job_completed event", ErrMissingField)
	}
	completedAt, err := time.Parse(time.RFC3339, j.CompletedAt)
	if err != nil {
		return fmt.Errorf("%w: failed to parse completed_at: %v", ErrInvalidTimestamp, err)
	}

	if err := c.db.UpdateJobCompleted(ctx, platform, strconv.Itoa(j.ID), completedAt, c.extractRaw(j.Status, body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on completion, inserting missing job", "job_id", j.ID)
			return c.insertJobToDB(ctx, j, body)
		}
		return fmt.Errorf("failed to update job completed in database: %w", err)
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
