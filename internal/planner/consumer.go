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

var supportedActions = []string{"queued", "in_progress", "completed"}

func NewJobConsumer(consumer queue.Consumer, db JobDatabase, metrics *Metrics) *JobConsumer {
	return &JobConsumer{
		consumer: consumer,
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

// getWorkflowJob extracts and validates a workflow job from a webhook message.
// Returns nil for events that should be ignored (non-workflow_job, unsupported actions, non-self-hosted).
// Returns an error only for malformed data that cannot be processed.
//
//nolint:cyclop // to be addressed in follow-up PR
func getWorkflowJob(ctx context.Context, headers map[string]interface{}, body []byte) (*githubWebhookJob, error) {
	// Parse webhook event from headers and body
	jobEvent, err := parseWebhookEvent(ctx, headers, body)
	if err != nil {
		return nil, err
	}
	if jobEvent == nil {
		return nil, nil // Event should be ignored
	}

	// Apply business rules to filter jobs
	shouldProcess, err := shouldProcessJob(ctx, jobEvent)
	if err != nil {
		return nil, err
	}
	if !shouldProcess {
		return nil, nil // Job should be ignored
	}

	// Validate required fields are present
	job := jobEvent.GetWorkflowJob()
	action := jobEvent.GetAction()
	if err := validateJobFields(job, action); err != nil {
		return nil, err
	}

	// Build final webhook job structure
	return buildWebhookJob(jobEvent, body)
}

// parseWebhookEvent extracts the event type from headers and parses the webhook body.
// Returns (nil, nil) for non-workflow_job events (should be ignored).
// Returns error only for malformed webhooks.
func parseWebhookEvent(ctx context.Context, headers map[string]interface{}, body []byte) (*github.WorkflowJobEvent, error) {
	// Extract and validate X-GitHub-Event header
	eventTypeHeader, ok := headers[githubEventHeaderKey]
	if !ok {
		return nil, fmt.Errorf("missing X-GitHub-Event header")
	}

	eventType, ok := eventTypeHeader.(string)
	if !ok {
		return nil, fmt.Errorf("X-GitHub-Event must be string")
	}

	// Parse webhook payload
	event, err := github.ParseWebHook(eventType, body)
	if err != nil {
		return nil, fmt.Errorf("unable to parse webhook: %w", err)
	}

	// Type assert to WorkflowJobEvent
	jobEvent, ok := event.(*github.WorkflowJobEvent)
	if !ok {
		if eventType == "workflow_job" {
			logger.WarnContext(ctx, "received workflow_job in \"X-GitHub-Event\" header but payload did not parse to expected type; possible GitHub API change or library issue")
		} else {
			logger.DebugContext(ctx, "ignoring non-workflow_job event", "event_type", eventType)
		}
		return nil, nil // Not an error, just ignore
	}

	return jobEvent, nil
}

// shouldProcessJob checks if the job should be processed based on action and labels.
// Returns (false, nil) if job should be ignored.
// Returns (false, error) if validation fails.
func shouldProcessJob(ctx context.Context, jobEvent *github.WorkflowJobEvent) (bool, error) {
	action := jobEvent.GetAction()

	// Check if action is supported
	if !slices.Contains(supportedActions, action) {
		logger.DebugContext(ctx, "ignoring workflow_job action", "action", action)
		return false, nil
	}

	job := jobEvent.GetWorkflowJob()
	if job == nil {
		return false, fmt.Errorf("missing workflow_job field in event webhook")
	}

	// Check if self-hosted
	if !isSelfHosted(job.Labels) {
		repo := jobEvent.GetRepo().GetFullName()
		logger.DebugContext(ctx, "ignoring non self-hosted job", "repo", repo, "labels", strings.Join(job.Labels, ","))
		return false, nil
	}

	return true, nil
}

// validateJobFields ensures all required fields are present for the job action.
func validateJobFields(job *github.WorkflowJob, action string) error {
	// Always required
	if job.GetCreatedAt().IsZero() {
		return fmt.Errorf("missing created_at in event webhook")
	}

	if job.GetID() == 0 {
		return fmt.Errorf("missing job id in event webhook")
	}

	// Action-specific validations
	if action == "in_progress" && job.GetStartedAt().IsZero() {
		return fmt.Errorf("missing started_at in in_progress event webhook")
	}

	if action == "completed" && job.GetCompletedAt().IsZero() {
		return fmt.Errorf("missing completed_at in completed event webhook")
	}

	return nil
}

// buildWebhookJob constructs a githubWebhookJob from validated GitHub event data.
func buildWebhookJob(jobEvent *github.WorkflowJobEvent, body []byte) (*githubWebhookJob, error) {
	job := jobEvent.GetWorkflowJob()
	action := jobEvent.GetAction()

	// Parse raw JSON for storage
	var rawJson map[string]interface{}
	if err := json.Unmarshal(body, &rawJson); err != nil {
		return nil, fmt.Errorf("invalid github webhook: %v", err)
	}

	// Extract required fields
	repo := jobEvent.GetRepo().GetFullName()
	if repo == "" {
		return nil, fmt.Errorf("missing repo full name in webhook payload")
	}

	id := strconv.FormatInt(job.GetID(), 10)

	return &githubWebhookJob{
		id:      id,
		repo:    repo,
		labels:  job.Labels,
		action:  action,
		payload: jobEvent,
		job: &database.Job{
			ID:          id,
			Platform:    platform,
			Labels:      job.Labels,
			CreatedAt:   job.GetCreatedAt().Time,
			StartedAt:   parseOptionalGitHubTime(job.StartedAt),
			CompletedAt: parseOptionalGitHubTime(job.CompletedAt),
			Raw:         map[string]interface{}{action: rawJson},
		},
	}, nil
}

// isSelfHosted checks if the job labels indicate it's for self-hosted runners.
func isSelfHosted(labels []string) bool {
	for _, label := range labels {
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

	job, err := getWorkflowJob(ctx, msg.Headers, msg.Body)
	if err != nil {
		logger.ErrorContext(ctx, "cannot parse webhook payload, discarding to DLQ", "error", err)
		span.RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
		c.discardMessage(ctx, &msg)
		return err
	}

	if job == nil {
		c.metrics.ObserveDiscardedWebhook(ctx, platform)
		c.ignoreMessage(ctx, &msg)
		return nil
	}

	err = c.handleMessage(ctx, job)
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
}

func (c *JobConsumer) ignoreMessage(ctx context.Context, delivery *amqp.Delivery) {
	err := delivery.Ack(false)
	if err != nil {
		logger.ErrorContext(ctx, "cannot ignore queue message", "error", err)
		oteltrace.SpanFromContext(ctx).RecordError(err)
		c.metrics.ObserveWebhookError(ctx, platform)
	}
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
