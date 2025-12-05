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
	"errors"
	"fmt"
	"log/slog"
	"strconv"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/google/go-github/v67/github"
	amqp "github.com/rabbitmq/amqp091-go"
)

const (
	platform             = "github"
	githubEventHeaderKey = "X-GitHub-Event"
)

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

			err := c.handleMessage(ctx, msg.Headers, msg.Body)
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

// handleMessage processes a single AMQP message with headers and body.
func (c *AmqpConsumer) handleMessage(ctx context.Context, headers amqp.Table, body []byte) error {
	// Extract the event type from headers
	eventTypeHeader, ok := headers[githubEventHeaderKey]
	if !ok {
		c.logger.Warn("missing X-GitHub-Event header, discarding message")
		return classifyError(fmt.Errorf("%w: X-GitHub-Event header", ErrMissingField))
	}

	eventType, ok := eventTypeHeader.(string)
	if !ok {
		c.logger.Warn("X-GitHub-Event header is not a string, discarding message")
		return classifyError(fmt.Errorf("%w: X-GitHub-Event must be string", ErrInvalidHeader))
	}

	// Parse the webhook using go-github library
	event, err := github.ParseWebHook(eventType, body)
	if err != nil {
		return classifyError(fmt.Errorf("%w: %v", ErrInvalidJSON, err))
	}

	// Check if it's a workflow_job event
	jobEvent, ok := event.(*github.WorkflowJobEvent)
	if !ok {
		c.logger.Info("event is not a workflow_job, discarding", "event_type", eventType)
		return classifyError(fmt.Errorf("%w: %s", ErrUnsupportedEvent, eventType))
	}

	// Process the workflow job event based on action
	action := jobEvent.GetAction()
	switch action {
	case "queued":
		err = c.insertJobToDB(ctx, jobEvent, body)
	case "waiting":
		return nil
	case "in_progress":
		err = c.updateJobStartedInDB(ctx, jobEvent, body)
	case "completed":
		err = c.updateJobCompletedInDB(ctx, jobEvent, body)
	default:
		c.logger.Warn("ignoring other action type", "action", action)
		return classifyError(fmt.Errorf("%w: %s", ErrUnknownAction, action))
	}

	// Classify the error to determine if it should be retried
	if err != nil {
		return classifyError(err)
	}
	return nil
}

// insertJobToDB inserts a new job into the database.
func (c *AmqpConsumer) insertJobToDB(ctx context.Context, jobEvent *github.WorkflowJobEvent, body []byte) error {
	job := jobEvent.GetWorkflowJob()
	if job == nil {
		return fmt.Errorf("%w: workflow_job field", ErrMissingField)
	}

	createdAt := job.GetCreatedAt()
	if createdAt.IsZero() {
		return fmt.Errorf("%w: created_at in job_queued event", ErrMissingField)
	}

	dbJob := &database.Job{
		ID:          strconv.FormatInt(job.GetID(), 10),
		Platform:    platform,
		Labels:      job.Labels,
		CreatedAt:   createdAt.Time,
		StartedAt:   c.parseOptionalGitHubTime(job.StartedAt),
		CompletedAt: c.parseOptionalGitHubTime(job.CompletedAt),
		Raw:         c.extractRaw(jobEvent, body),
	}

	if err := c.db.AddJob(ctx, dbJob); err != nil {
		if errors.Is(err, database.ErrExist) {
			c.logger.Info("job already exists in database", "job_id", job.GetID())
			return fmt.Errorf("%w: job %d", ErrJobAlreadyExists, job.GetID())
		}
		return fmt.Errorf("failed to add job to database: %w", err)
	}

	return nil
}

// parseOptionalGitHubTime parses an optional GitHub timestamp, returning nil if not set.
func (c *AmqpConsumer) parseOptionalGitHubTime(ts *github.Timestamp) *time.Time {
	if ts == nil || ts.IsZero() {
		return nil
	}
	t := ts.Time
	return &t
}

// updateJobStartedInDB updates the job's started_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *AmqpConsumer) updateJobStartedInDB(ctx context.Context, jobEvent *github.WorkflowJobEvent, body []byte) error {
	job := jobEvent.GetWorkflowJob()
	if job == nil {
		return fmt.Errorf("%w: workflow_job field", ErrMissingField)
	}

	startedAt := job.GetStartedAt()
	if startedAt.IsZero() {
		return fmt.Errorf("%w: started_at in job_in_progress event", ErrMissingField)
	}

	if err := c.db.UpdateJobStarted(ctx, platform, strconv.FormatInt(job.GetID(), 10), startedAt.Time, c.extractRaw(jobEvent, body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on start, inserting missing job", "job_id", job.GetID())
			return c.insertJobToDB(ctx, jobEvent, body)
		}
		return fmt.Errorf("failed to update job started in database: %w", err)
	}

	return nil
}

// updateJobCompletedInDB updates the job's completed_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *AmqpConsumer) updateJobCompletedInDB(ctx context.Context, jobEvent *github.WorkflowJobEvent, body []byte) error {
	job := jobEvent.GetWorkflowJob()
	if job == nil {
		return fmt.Errorf("%w: workflow_job field", ErrMissingField)
	}

	completedAt := job.GetCompletedAt()
	if completedAt.IsZero() {
		return fmt.Errorf("%w: completed_at in job_completed event", ErrMissingField)
	}

	if err := c.db.UpdateJobCompleted(ctx, platform, strconv.FormatInt(job.GetID(), 10), completedAt.Time, c.extractRaw(jobEvent, body)); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			c.logger.Warn("job not found in database on completion, inserting missing job", "job_id", job.GetID())
			return c.insertJobToDB(ctx, jobEvent, body)
		}
		return fmt.Errorf("failed to update job completed in database: %w", err)
	}

	return nil
}

// extractRaw returns a map with the action type as the key and the
// stringified raw message body as the value.
func (c *AmqpConsumer) extractRaw(jobEvent *github.WorkflowJobEvent, body []byte) map[string]any {
	payload := map[string]any{
		jobEvent.GetAction(): string(body),
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
