package planner

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/queue"
	"github.com/google/go-github/v80/github"
	amqp "github.com/rabbitmq/amqp091-go"
)

type JobDatabase interface {
	AddJob(ctx context.Context, job *database.Job) error
	UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]any) error
	UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]any) error
}

type JobConsumer struct {
	consumer queue.Consumer
	db       JobDatabase

	metrics *Metrics
}

const (
	platform             = "github"
	githubEventHeaderKey = "X-GitHub-Event"
)

func NewJobConsumer(amqpUri, queueName string, db JobDatabase, metrics *Metrics) *JobConsumer {
	return &JobConsumer{
		consumer: queue.NewAmqpConsumer(amqpUri, queueName),
		db:       db,
		metrics:  metrics,
	}
}

// Start begins consuming messages from the AMQP queue and processing them.
func (c *JobConsumer) Start(ctx context.Context) error {
	logger.InfoContext(ctx, "start consume workflow jobs from queue")

	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		msg, err := c.consumer.Pull(ctx)
		if err != nil {
			logger.ErrorContext(ctx, "cannot receive message from amqp, retrying", "error", err)
			c.metrics.ObserveWebhookError(ctx, platform)
			continue
		}

		err = c.handleMessage(ctx, msg.Headers, msg.Body)
		if err == nil {
			if err := msg.Ack(false); err != nil {
				logger.ErrorContext(ctx, "cannot ack queue message", "error", err)
				c.metrics.ObserveWebhookError(ctx, platform)
			}
			continue
		}

		if errors.Is(err, ErrNonRetryable) {
			c.metrics.ObserveWebhookError(ctx, platform)
			c.metrics.ObserveDiscardedWebhook(ctx, platform)
			// don't requeue
			if err := msg.Nack(false, false); err != nil {
				logger.ErrorContext(ctx, "cannot nack message without requeue", "error", err)
				c.metrics.ObserveWebhookError(ctx, platform)
			}
			logger.ErrorContext(ctx, "failed to handle message without requeue", "error", err)
			continue
		}
		// Other errors are requeued by default
		logger.ErrorContext(ctx, "failed to handle message, requeuing", "error", err)
		c.metrics.ObserveWebhookError(ctx, platform)
		// requeue
		if err := msg.Nack(false, true); err != nil {
			logger.ErrorContext(ctx, "cannot nack message with requeue", "error", err)
			c.metrics.ObserveWebhookError(ctx, platform)
		}
	}
}

// handleMessage processes a single AMQP message with headers and body.
func (c *JobConsumer) handleMessage(ctx context.Context, headers amqp.Table, body []byte) error {
	// Extract the event type from headers
	eventTypeHeader, ok := headers[githubEventHeaderKey]
	if !ok {
		logger.WarnContext(ctx, "missing X-GitHub-Event header, discarding message")
		return classifyError(fmt.Errorf("%w: X-GitHub-Event header", ErrMissingField))
	}

	eventType, ok := eventTypeHeader.(string)
	if !ok {
		logger.WarnContext(ctx, "X-GitHub-Event header is not a string, discarding message")
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
		logger.InfoContext(ctx, "event is not a workflow_job, discarding", "event_type", eventType)
		return classifyError(fmt.Errorf("%w: %s", ErrUnsupportedEvent, eventType))
	}

	// Process the workflow job event based on action
	action := jobEvent.GetAction()
	switch action {
	case "queued":
		err = c.insertJobToDB(ctx, jobEvent, body)
		if err != nil {
			c.metrics.ObserveProcessedGitHubWebhook(ctx, jobEvent)
		}
	case "waiting":
		c.metrics.ObserveDiscardedWebhook(ctx, platform)
		return nil
	case "in_progress":
		err = c.updateJobStartedInDB(ctx, jobEvent, body)
		if err != nil {
			c.metrics.ObserveProcessedGitHubWebhook(ctx, jobEvent)
		}
	case "completed":
		err = c.updateJobCompletedInDB(ctx, jobEvent, body)
		if err != nil {
			c.metrics.ObserveProcessedGitHubWebhook(ctx, jobEvent)
		}
	default:
		logger.WarnContext(ctx, "ignoring other action type", "action", action)
		return classifyError(fmt.Errorf("%w: %s", ErrUnknownAction, action))
	}

	// Classify the error to determine if it should be retried
	if err != nil {
		return classifyError(err)
	}
	return nil
}

// insertJobToDB inserts a new job into the database.
func (c *JobConsumer) insertJobToDB(ctx context.Context, jobEvent *github.WorkflowJobEvent, body []byte) error {
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
			logger.InfoContext(ctx, "job already exists in database", "job_id", job.GetID())
			return fmt.Errorf("%w: job %d", ErrJobAlreadyExists, job.GetID())
		}
		return fmt.Errorf("failed to add job to database: %w", err)
	}

	return nil
}

// parseOptionalGitHubTime parses an optional GitHub timestamp, returning nil if not set.
func (c *JobConsumer) parseOptionalGitHubTime(ts *github.Timestamp) *time.Time {
	if ts == nil || ts.IsZero() {
		return nil
	}
	t := ts.Time
	return &t
}

// updateJobStartedInDB updates the job's started_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *JobConsumer) updateJobStartedInDB(ctx context.Context, jobEvent *github.WorkflowJobEvent, body []byte) error {
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
			logger.WarnContext(ctx, "job not found in database on start, inserting missing job", "job_id", job.GetID())
			return c.insertJobToDB(ctx, jobEvent, body)
		}
		return fmt.Errorf("failed to update job started in database: %w", err)
	}

	return nil
}

// updateJobCompletedInDB updates the job's completed_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *JobConsumer) updateJobCompletedInDB(ctx context.Context, jobEvent *github.WorkflowJobEvent, body []byte) error {
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
			logger.WarnContext(ctx, "job not found in database on completion, inserting missing job", "job_id", job.GetID())
			return c.insertJobToDB(ctx, jobEvent, body)
		}
		return fmt.Errorf("failed to update job completed in database: %w", err)
	}

	return nil
}

// extractRaw returns a map with the action type as the key and the
// stringified raw message body as the value.
func (c *JobConsumer) extractRaw(jobEvent *github.WorkflowJobEvent, body []byte) map[string]any {
	payload := map[string]any{
		jobEvent.GetAction(): string(body),
	}
	return payload
}
