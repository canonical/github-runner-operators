package planner

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/queue"
	"github.com/google/go-github/v81/github"
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

const (
	platform             = "github"
	githubEventHeaderKey = "X-GitHub-Event"
	maxBackoff           = 5 * time.Minute
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
		return githubWebhookJob{}, fmt.Errorf("missing X-GitHub-Event header")
	}

	eventType, ok := eventTypeHeader.(string)
	if !ok {
		logger.WarnContext(ctx, "X-GitHub-Event header is not a string, discarding message")
		return githubWebhookJob{}, fmt.Errorf("X-GitHub-Event must be string")
	}

	// Parse the webhook using go-github library
	event, err := github.ParseWebHook(eventType, body)
	if err != nil {
		return githubWebhookJob{}, fmt.Errorf("unable to parse webhook: %w", err)
	}

	// Check if it's a workflow_job event
	jobEvent, ok := event.(*github.WorkflowJobEvent)
	if !ok {
		logger.InfoContext(ctx, "event is not a workflow_job, discarding", "event_type", eventType)
		return githubWebhookJob{}, fmt.Errorf("unsupported webhook event: %s", eventType)
	}

	// Process the workflow job event based on action
	action := jobEvent.GetAction()
	if !slices.Contains([]string{"queued", "in_progress", "completed", "waiting"}, action) {
		return githubWebhookJob{}, fmt.Errorf("unknown webhook event action: %s", action)
	}

	job := jobEvent.GetWorkflowJob()
	if job == nil {
		return githubWebhookJob{}, fmt.Errorf("missing workflow_job field in event webhook")
	}

	createdAt := job.GetCreatedAt()
	if createdAt.IsZero() {
		return githubWebhookJob{}, fmt.Errorf("missing created_at in queued event webhook")
	}

	startedAt := job.GetStartedAt()
	if startedAt.IsZero() && action == "in_progress" {
		return githubWebhookJob{}, fmt.Errorf("missing started_at in in_progress event webhook")
	}

	completedAt := job.GetCompletedAt()
	if completedAt.IsZero() && action == "completed" {
		return githubWebhookJob{}, fmt.Errorf("missing completed_at in completed event webhook")
	}

	id := strconv.FormatInt(job.GetID(), 10)
	if id == "0" {
		return githubWebhookJob{}, fmt.Errorf("missing job id in event webhook")
	}

	var rawJson map[string]interface{}
	err = json.Unmarshal(body, &rawJson)
	if err != nil {
		return githubWebhookJob{}, fmt.Errorf("invalid github webhook: %v", err)
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
		return githubWebhookJob{}, fmt.Errorf("missing repo full name in webhook payload")
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

// isSelfHosted checks if the job is intended for self-hosted runners.
func isSelfHosted(job *githubWebhookJob) bool {
	for _, label := range job.labels {
		if strings.Contains(label, "self-hosted") {
			return true
		}
	}
	return false
}

type JobConsumer struct {
	consumer queue.Consumer
	db       JobDatabase

	started        sync.Mutex
	currentBackoff time.Duration

	metrics *Metrics
}

// Start begins consuming messages from the AMQP queue and processing them.
func (c *JobConsumer) Start(ctx context.Context) error {
	logger.InfoContext(ctx, "start consume workflow jobs from queue")
	c.started.Lock()
	defer c.started.Unlock()
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		_ = c.pullMessage(ctx)
	}
}

func (c *JobConsumer) Close() error {
	return c.consumer.Close()
}

func (c *JobConsumer) backoff(ctx context.Context) {
	if c.currentBackoff == 0 {
		c.currentBackoff = 1 * time.Second
	}
	select {
	case <-ctx.Done():
	case <-time.After(c.currentBackoff):
	}
	c.currentBackoff = min(maxBackoff, c.currentBackoff*2)
}

func (c *JobConsumer) clearBackoff() {
	c.currentBackoff = 0
}

// pullMessage receive one message from the AMQP queue and process it.
// pullMessage can return errors, but it's mostly for testing and can be ignored,
// as all errors are handled internally before return.
func (c *JobConsumer) pullMessage(ctx context.Context) error {
	msg, err := c.consumer.Pull(ctx)
	if err != nil {
		logger.ErrorContext(ctx, "cannot receive message from amqp, retrying", "error", err)
		c.metrics.ObserveWebhookError(ctx, platform)
		return err
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
		logger.ErrorContext(ctx, "cannot parse webhook payload", "error", err)
		span.RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
		c.discardMessage(ctx, &msg)
		return err
	}

	if !slices.Contains([]string{"queued", "in_progress", "completed"}, job.action) {
		logger.InfoContext(ctx, "ignore other action types for GitHub webhook job", "action", job.action)
		c.metrics.ObserveDiscardedWebhook(ctx, platform)
		c.discardMessage(ctx, &msg)
		return nil
	}

	if !isSelfHosted(&job) {
		logger.InfoContext(ctx, "ignore non self-hosted job", "repo", job.repo, "labels", strings.Join(job.labels, ","))
		c.metrics.ObserveDiscardedWebhook(ctx, platform)
		c.discardMessage(ctx, &msg)
		return nil
	}

	err = c.handleMessage(ctx, &job)
	if err == nil {
		c.consumedMessage(ctx, &msg)
		c.metrics.ObserveConsumedGitHubWebhook(ctx, job.payload)
		c.clearBackoff()
		return nil
	}

	span.RecordError(err)
	c.metrics.ObserveWebhookError(ctx, platform)
	c.requeueMessage(ctx, &msg)
	c.backoff(ctx)
	return err
}

func (c *JobConsumer) discardMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Nack(false, false)
	if err != nil {
		logger.ErrorContext(ctx, "cannot discard queue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
	}
	return
}

func (c *JobConsumer) consumedMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Ack(false)
	if err != nil {
		logger.ErrorContext(ctx, "cannot ack queue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
	}
}

func (c *JobConsumer) requeueMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Nack(false, true)
	if err != nil {
		logger.ErrorContext(ctx, "cannot requeue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
	}
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
			logger.InfoContext(ctx, "job already exists in database", "job_id", job.id)
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
