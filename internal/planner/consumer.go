package planner

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/queue"
	"github.com/google/go-github/v80/github"
	amqp "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	oteltrace "go.opentelemetry.io/otel/trace"
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

type githubWebhookJob struct {
	id     string
	repo   string
	labels []string
	action string

	payload *github.WorkflowJobEvent

	job *database.Job
}

// parseOptionalGitHubTime parses an optional GitHub timestamp, returning nil if not set.
func parseOptionalGitHubTime(ts *github.Timestamp) *time.Time {
	if ts == nil || ts.IsZero() {
		return nil
	}
	t := ts.Time
	return &t
}

func parseGithubWebhookPayload(ctx context.Context, headers map[string]interface{}, body []byte) (githubWebhookJob, error) {
	// Extract the event type from headers
	eventTypeHeader, ok := headers[githubEventHeaderKey]
	if !ok {
		logger.WarnContext(ctx, "missing X-GitHub-Event header, discarding message")
		return githubWebhookJob{}, fmt.Errorf("%w: X-GitHub-Event header", ErrMissingField)
	}

	eventType, ok := eventTypeHeader.(string)
	if !ok {
		logger.WarnContext(ctx, "X-GitHub-Event header is not a string, discarding message")
		return githubWebhookJob{}, fmt.Errorf("%w: X-GitHub-Event must be string", ErrInvalidHeader)
	}

	// Parse the webhook using go-github library
	event, err := github.ParseWebHook(eventType, body)
	if err != nil {
		return githubWebhookJob{}, fmt.Errorf("%w: %v", ErrInvalidJSON, err)
	}

	// Check if it's a workflow_job event
	jobEvent, ok := event.(*github.WorkflowJobEvent)
	if !ok {
		logger.InfoContext(ctx, "event is not a workflow_job, discarding", "event_type", eventType)
		return githubWebhookJob{}, fmt.Errorf("%w: %s", ErrUnsupportedEvent, eventType)
	}

	// Process the workflow job event based on action
	action := jobEvent.GetAction()
	if !slices.Contains([]string{"queued", "in_progress", "completed", "waiting"}, action) {
		return githubWebhookJob{}, fmt.Errorf("%w: %s", ErrUnknownAction, action)
	}

	job := jobEvent.GetWorkflowJob()
	if job == nil {
		return githubWebhookJob{}, fmt.Errorf("%w: workflow_job field", ErrMissingField)
	}

	createdAt := job.GetCreatedAt()
	if createdAt.IsZero() {
		return githubWebhookJob{}, fmt.Errorf("%w: created_at in job_queued event", ErrMissingField)
	}

	startedAt := job.GetStartedAt()
	if startedAt.IsZero() && action == "in_progress" {
		return githubWebhookJob{}, fmt.Errorf("%w: started_at in job_in_progress event", ErrMissingField)
	}

	completedAt := job.GetCompletedAt()
	if completedAt.IsZero() && action == "completed" {
		return githubWebhookJob{}, fmt.Errorf("%w: completed_at in job_completed event", ErrMissingField)
	}

	id := strconv.FormatInt(job.GetID(), 10)
	if id == "0" {
		return githubWebhookJob{}, fmt.Errorf("%w: job ID", ErrMissingField)
	}

	var rawJson map[string]interface{}
	err = json.Unmarshal(body, &rawJson)
	if err != nil {
		return githubWebhookJob{}, fmt.Errorf("%w: %v", ErrInvalidJSON, err)
	}

	dbJob := &database.Job{
		ID:          id,
		Platform:    platform,
		Labels:      job.Labels,
		CreatedAt:   createdAt.Time,
		StartedAt:   parseOptionalGitHubTime(job.StartedAt),
		CompletedAt: parseOptionalGitHubTime(job.CompletedAt),
		Raw:         map[string]interface{}{action: rawJson},
	}

	repo := jobEvent.GetRepo().GetFullName()

	if repo == "" {
		return githubWebhookJob{}, fmt.Errorf("%w: repo full name", ErrMissingField)
	}

	return githubWebhookJob{
		id:     id,
		repo:   jobEvent.GetRepo().GetFullName(),
		labels: job.Labels,
		action: action,

		payload: jobEvent,

		job: dbJob,
	}, nil
}

// Start begins consuming messages from the AMQP queue and processing them.
func (c *JobConsumer) Start(ctx context.Context) error {
	logger.InfoContext(ctx, "start consume workflow jobs from queue")
	backoff := time.Second
	for {
		c.pullMessage(ctx)
		select {
		case <-time.After(backoff):
		case <-ctx.Done():
			return ctx.Err()
		}
		backoff = min(5*time.Minute, backoff*2)
	}
}

func (c *JobConsumer) pullMessage(ctx context.Context) {
	msg, err := c.consumer.Pull(ctx)
	if err != nil {
		logger.ErrorContext(ctx, "cannot receive message from amqp, retrying", "error", err)
		c.metrics.ObserveWebhookError(ctx, platform)
		return
	}
	headers := make(map[string]string)
	for h, v := range msg.Headers {
		if strVal, ok := v.(string); ok {
			headers[h] = strVal
		}
	}
	ctx = otel.GetTextMapPropagator().Extract(ctx, propagation.MapCarrier(headers))
	ctx, span := trace.Start(ctx, "consume webhook")
	defer span.End()

	job, err := parseGithubWebhookPayload(ctx, msg.Headers, msg.Body)
	if err != nil {
		span.RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
		c.discardMessage(ctx, &msg)
		return
	}

	if !slices.Contains([]string{"queued", "in_progress", "completed"}, job.action) {
		logger.InfoContext(ctx, "ignore other action types for GitHub webhook job", "action", job.action)
		c.metrics.ObserveDiscardedWebhook(ctx, platform)
		c.discardMessage(ctx, &msg)
		return
	}

	isSelfHosted := false
	for _, label := range job.labels {
		if strings.Contains(label, "self-hosted") {
			isSelfHosted = true
			break
		}
	}
	if !isSelfHosted {
		logger.InfoContext(ctx, "ignore non self-hosted job", "repo", job.repo, "labels", strings.Join(job.labels, ","))
		c.metrics.ObserveDiscardedWebhook(ctx, platform)
		c.discardMessage(ctx, &msg)
		return
	}

	err = c.handleMessage(ctx, &job)
	if err == nil {
		c.consumedMessage(ctx, &msg)
		c.metrics.ObserveConsumedGitHubWebhook(ctx, job.payload)
		return
	}

	span.RecordError(err)
	c.metrics.ObserveWebhookError(ctx, platform)
	c.requeueMessage(ctx, &msg)
	return
}

func (c *JobConsumer) discardMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Nack(false, false)
	if err != nil {
		logger.ErrorContext(ctx, "cannot discard queue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
	}
	c.metrics.ObserveWebhookError(ctx, platform)
	return
}

func (c *JobConsumer) consumedMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Ack(false)
	if err != nil {
		logger.ErrorContext(ctx, "cannot ack queue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
	}
	c.metrics.ObserveWebhookError(ctx, platform)
}

func (c *JobConsumer) requeueMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Nack(false, true)
	if err != nil {
		logger.ErrorContext(ctx, "cannot requeue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
	}
	c.metrics.ObserveWebhookError(ctx, platform)
}

// handleMessage processes a single AMQP message with headers and body.
func (c *JobConsumer) handleMessage(ctx context.Context, job *githubWebhookJob) error {
	switch job.action {
	case "queued":
		return c.insertJobToDB(ctx, job)
	case "in_progress":
		return c.updateJobStartedInDB(ctx, job)
	case "completed":
		return c.updateJobCompletedInDB(ctx, job)
	}
	return nil
}

// insertJobToDB inserts a new job into the database.
func (c *JobConsumer) insertJobToDB(ctx context.Context, job *githubWebhookJob) error {
	if err := c.db.AddJob(ctx, job.job); err != nil {
		if errors.Is(err, database.ErrExist) {
			logger.ErrorContext(ctx, "job already exists in database", "job_id", job.id)
			return nil
		}
		return fmt.Errorf("failed to add job to database: %w", err)
	}

	return nil
}

// updateJobStartedInDB updates the job's started_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *JobConsumer) updateJobStartedInDB(ctx context.Context, job *githubWebhookJob) error {
	if err := c.db.UpdateJobStarted(ctx, platform, job.id, *job.job.StartedAt, job.job.Raw); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			logger.WarnContext(ctx, "job not found in database on start, inserting missing job", "job_id", job.id)
			return c.insertJobToDB(ctx, job)
		}
		return fmt.Errorf("failed to update job started in database: %w", err)
	}

	return nil
}

// updateJobCompletedInDB updates the job's completed_at timestamp in the database.
// If the job does not exist, it inserts the missing job to the database.
func (c *JobConsumer) updateJobCompletedInDB(ctx context.Context, job *githubWebhookJob) error {
	if err := c.db.UpdateJobCompleted(ctx, platform, job.id, *job.job.CompletedAt, job.job.Raw); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			logger.WarnContext(ctx, "job not found in database on completion, inserting missing job", "job_id", job.id)
			return c.insertJobToDB(ctx, job)
		}
		return fmt.Errorf("failed to update job completed in database: %w", err)
	}

	return nil
}
