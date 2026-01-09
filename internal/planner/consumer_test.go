/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit tests for the consumer.
 */

package planner

import (
	"context"
	"encoding/json"
	"errors"
	"maps"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/canonical/github-runner-operators/internal/telemetry"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

type fakeDB struct {
	jobs              map[string]*database.Job
	addErr            error
	updateStartErr    error
	updateCompleteErr error
}

func newFakeDB() *fakeDB {
	return &fakeDB{jobs: make(map[string]*database.Job)}
}

func (db *fakeDB) AddJob(ctx context.Context, job *database.Job) error {
	if db.addErr != nil {
		return db.addErr
	}

	key := jobKey(job.Platform, job.ID)
	if _, exists := db.jobs[key]; exists {
		return database.ErrExist
	}
	db.jobs[key] = job
	return nil
}

func (db *fakeDB) UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]any) error {
	if db.updateStartErr != nil {
		return db.updateStartErr
	}

	key := jobKey(platform, id)
	job, exists := db.jobs[key]
	if !exists {
		return database.ErrNotExist
	}
	job.StartedAt = &startedAt
	mergeRaw(job, raw)
	return nil
}

func (db *fakeDB) UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]any) error {
	if db.updateCompleteErr != nil {
		return db.updateCompleteErr
	}
	key := jobKey(platform, id)
	job, exists := db.jobs[key]
	if !exists {
		return database.ErrNotExist
	}
	job.CompletedAt = &completedAt
	mergeRaw(job, raw)
	return nil
}

func mergeRaw(job *database.Job, raw map[string]interface{}) {
	if raw == nil {
		return
	}
	if job.Raw == nil {
		job.Raw = raw
		return
	}
	maps.Copy(job.Raw, raw)
}

func jobKey(platform, id string) string { return platform + ":" + id }

// fakeAmqpConsumer mocks the queue.AmqpConsumer for testing JobConsumer
type fakeAmqpConsumer struct {
	deliveries <-chan amqp.Delivery
	pullErr    error
}

func (c *fakeAmqpConsumer) Pull(ctx context.Context) (amqp.Delivery, error) {
	if c.pullErr != nil {
		return amqp.Delivery{}, c.pullErr
	}

	select {
	case msg, ok := <-c.deliveries:
		if !ok {
			// Channel closed, wait for context to be done
			<-ctx.Done()
			return amqp.Delivery{}, ctx.Err()
		}
		return msg, nil
	case <-ctx.Done():
		return amqp.Delivery{}, ctx.Err()
	}
}

func (c *fakeAmqpConsumer) Close() error {
	return nil
}

func TestConsumer(t *testing.T) {
	/*
		arrange: setup test environment with fake database, consumer, and metrics
		act: pull and process the message from the queue
		assert: check error state, database changes, and metrics
	*/
	mk := func(m map[string]any) []byte { b, _ := json.Marshal(m); return b }
	tests := []struct {
		name         string
		setupDB      func(*fakeDB)
		delivery     amqp.Delivery
		pullErr      error
		expectErr    bool
		checkDB      func(*testing.T, *fakeDB)
		checkMetrics func(*testing.T, *telemetry.TestMetricReader)
	}{{
		name:    "succeeds when queued job is inserted",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "queued",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         1,
					"labels":     []string{"self-hosted", "linux"},
					"status":     "queued",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:1"], "job not inserted")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from ack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 1.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name: "skips insert when queued job already exists",
		setupDB: func(db *fakeDB) {
			db.jobs["github:2"] = &database.Job{ID: "2", Platform: "github"}
		},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "queued",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         2,
					"labels":     []string{"self-hosted", "x"},
					"status":     "queued",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:2"], "job not found")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from ack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 1.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name: "succeeds when job updated to in_progress",
		setupDB: func(db *fakeDB) {
			db.jobs["github:3"] = &database.Job{ID: "3", Platform: "github", Raw: map[string]any{}}
		},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "in_progress",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         3,
					"labels":     []string{"self-hosted"},
					"status":     "in_progress",
					"created_at": "2025-01-01T23:00:00Z",
					"started_at": "2025-01-02T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:3"], "job not found")
			assert.NotNil(t, db.jobs["github:3"].StartedAt, "started_at not set")
			assert.Equal(t, "2025-01-02T00:00:00Z", db.jobs["github:3"].StartedAt.Format(time.RFC3339), "started_at incorrect")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from ack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 1.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "insert and update when job not found on start",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "in_progress",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         21,
					"labels":     []string{"self-hosted"},
					"status":     "in_progress",
					"created_at": "2025-01-01T00:00:00Z",
					"started_at": "2025-01-02T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:21"], "job should be created on start when missing")
			assert.NotNil(t, db.jobs["github:21"].StartedAt, "started_at not set")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from ack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 1.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name: "succeeds when job updated to completed",
		setupDB: func(db *fakeDB) {
			db.jobs["github:5"] = &database.Job{ID: "5", Platform: "github"}
		},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "completed",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":           5,
					"labels":       []string{"self-hosted"},
					"status":       "completed",
					"created_at":   "2025-01-01T23:00:00Z",
					"started_at":   "2025-01-02T23:30:00Z",
					"completed_at": "2025-01-03T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:5"], "job not found")
			assert.NotNil(t, db.jobs["github:5"].CompletedAt, "completed_at not set")
			assert.Equal(t, "2025-01-03T00:00:00Z", db.jobs["github:5"].CompletedAt.Format(time.RFC3339), "completed_at incorrect")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from ack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 1.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "skips when JSON is invalid",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body:    []byte("{not-json}"),
		},
		expectErr: true,
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 2 errors: 1 from processing error, 1 from nack failure
			assert.Equal(t, 2.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "ignores when action is unknown",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "unknown",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         16,
					"labels":     []string{"l", "self-hosted"},
					"status":     "queued",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:16"], "job should not be inserted")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName)) // ack failure
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 1.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "requeues when AddJob fails with other error",
		setupDB: func(db *fakeDB) { db.addErr = errors.New("db down") },
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "queued",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         10,
					"labels":     []string{"l", "self-hosted"},
					"status":     "queued",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: true,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:10"], "job should not be inserted")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 2 errors: 1 from processing error, 1 from nack failure
			assert.Equal(t, 2.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "fails when started_at is invalid",
		setupDB: func(db *fakeDB) { db.jobs["github:11"] = &database.Job{ID: "11", Platform: "github"} },
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "in_progress",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         11,
					"labels":     []string{"self-hosted"},
					"status":     "in_progress",
					"started_at": "invalid",
				},
			}),
		},
		expectErr: true,
		checkDB: func(t *testing.T, db *fakeDB) {
			j := db.jobs["github:11"]
			assert.NotNil(t, j, "job should exist")
			assert.Nil(t, j.StartedAt, "started_at should not be set on invalid time")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 2 errors: 1 from processing error, 1 from nack failure
			assert.Equal(t, 2.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "fails when completed_at is invalid",
		setupDB: func(db *fakeDB) { db.jobs["github:12"] = &database.Job{ID: "12", Platform: "github"} },
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "completed",
				"workflow_job": map[string]any{
					"id":           12,
					"labels":       []string{"self-hosted"},
					"status":       "completed",
					"completed_at": "invalid",
				},
			}),
		},
		expectErr: true,
		checkDB: func(t *testing.T, db *fakeDB) {
			j := db.jobs["github:12"]
			assert.NotNil(t, j, "job should exist")
			assert.Nil(t, j.CompletedAt, "completed_at should not be set on invalid time")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 2 errors: 1 from processing error, 1 from nack failure
			assert.Equal(t, 2.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "insert and update when job not found on completion",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "completed",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":           22,
					"labels":       []string{"self-hosted"},
					"status":       "completed",
					"created_at":   "2025-01-01T00:00:00Z",
					"started_at":   "2025-01-02T00:00:00Z",
					"completed_at": "2025-01-03T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:22"], "job should be created on completion when missing")
			assert.NotNil(t, db.jobs["github:22"].CompletedAt, "completed_at not set")
			assert.Equal(t, "2025-01-03T00:00:00Z", db.jobs["github:22"].CompletedAt.Format(time.RFC3339), "completed_at incorrect")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from ack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 1.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "discards message when X-GitHub-Event header is missing",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{}, // No X-GitHub-Event header
			Body: mk(map[string]any{
				"action": "queued",
				"workflow_job": map[string]any{
					"id":         23,
					"labels":     []string{"linux"},
					"status":     "queued",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: true,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:23"], "job should not be inserted when header is missing")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 2 errors: 1 from processing error, 1 from nack failure
			assert.Equal(t, 2.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 0.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "ignores non-workflow_job events",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "pull_request"},
			Body: mk(map[string]any{
				"action": "opened",
				"pull_request": map[string]any{
					"id": 24,
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Empty(t, db.jobs, "no jobs should be inserted for non-workflow_job events")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName)) // ack failure
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 1.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "discards non-self-hosted jobs",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "queued",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         25,
					"labels":     []string{"ubuntu-latest"},
					"status":     "queued",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:25"], "non-self-hosted job should not be inserted")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from nack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 1.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}, {
		name:    "ignores waiting action",
		setupDB: func(db *fakeDB) {},
		delivery: amqp.Delivery{
			Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
			Body: mk(map[string]any{
				"action": "waiting",
				"repository": map[string]any{
					"full_name": "canonical/test",
				},
				"workflow_job": map[string]any{
					"id":         26,
					"labels":     []string{"self-hosted"},
					"status":     "waiting",
					"created_at": "2025-01-01T00:00:00Z",
				},
			}),
		},
		expectErr: false,
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:26"], "waiting action should not be processed")
		},
		checkMetrics: func(t *testing.T, mr *telemetry.TestMetricReader) {
			m := mr.Collect(t)
			// 1 error from nack failure
			assert.Equal(t, 1.0, m.Counter(t, webhookErrorsMetricName))
			assert.Equal(t, 0.0, m.Counter(t, consumedWebhooksMetricName))
			assert.Equal(t, 1.0, m.Counter(t, discardedWebhooksMetricName))
		},
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mr := telemetry.AcquireTestMetricReader(t)
			defer telemetry.ReleaseTestMetricReader(t)

			db := newFakeDB()
			tt.setupDB(db)

			ch := make(chan amqp.Delivery, 1)
			ch <- tt.delivery
			close(ch)

			fakeConsumer := &fakeAmqpConsumer{
				deliveries: ch,
				pullErr:    tt.pullErr,
			}
			consumer := &JobConsumer{
				consumer: fakeConsumer,
				db:       db,
				metrics:  NewMetrics(&fakeStore{}),
			}

			ctx := context.Background()
			err := consumer.pullMessage(ctx)

			if tt.expectErr {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
			if tt.checkDB != nil {
				tt.checkDB(t, db)
			}
			if tt.checkMetrics != nil {
				tt.checkMetrics(t, mr)
			}
		})
	}
}

func TestGetWorkflowJob(t *testing.T) {
	/*
		arrange: setup context for parsing webhook payload
		act: extract workflow job from GitHub webhook payload
		assert: check for expected errors, nil returns, and validate parsed job data
	*/
	mk := func(m map[string]any) []byte { b, _ := json.Marshal(m); return b }

	tests := []struct {
		name         string
		headers      map[string]interface{}
		body         []byte
		expectErr    bool
		expectErrMsg string
		expectNil    bool
		validateJob  func(*testing.T, *githubWebhookJob)
	}{{
		name: "successful parsing of queued event",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "queued",
			"repository": map[string]any{
				"full_name": "canonical/test-repo",
			},
			"workflow_job": map[string]any{
				"id":         100,
				"labels":     []string{"self-hosted", "linux"},
				"status":     "queued",
				"created_at": "2025-01-01T10:00:00Z",
			},
		}),
		validateJob: func(t *testing.T, job *githubWebhookJob) {
			assert.Equal(t, "100", job.id)
			assert.Equal(t, "canonical/test-repo", job.repo)
			assert.Equal(t, "queued", job.action)
			assert.ElementsMatch(t, []string{"self-hosted", "linux"}, job.labels)
			assert.NotNil(t, job.job)
			assert.Equal(t, "2025-01-01T10:00:00Z", job.job.CreatedAt.Format(time.RFC3339))
		},
	}, {
		name: "missing X-GitHub-Event header",
		headers: map[string]interface{}{
			"Other-Header": "value",
		},
		body:         mk(map[string]any{"action": "queued"}),
		expectErr:    true,
		expectErrMsg: "missing X-GitHub-Event header",
	}, {
		name: "X-GitHub-Event header is not a string",
		headers: map[string]interface{}{
			"X-GitHub-Event": 123, // Not a string
		},
		body:         mk(map[string]any{"action": "queued"}),
		expectErr:    true,
		expectErrMsg: "X-GitHub-Event must be string",
	}, {
		name: "unsupported event type",
		headers: map[string]interface{}{
			"X-GitHub-Event": "pull_request",
		},
		body: mk(map[string]any{
			"action": "opened",
			"pull_request": map[string]any{
				"id": 1,
			},
		}),
		expectNil: true,
	}, {
		name: "unknown action",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "cancelled",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				"id":         200,
				"labels":     []string{"self-hosted"},
				"created_at": "2025-01-01T10:00:00Z",
			},
		}),
		expectNil: true,
	}, {
		name: "non-self-hosted job",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "queued",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				"id":         250,
				"labels":     []string{"ubuntu-latest"}, // Not self-hosted
				"created_at": "2025-01-01T10:00:00Z",
			},
		}),
		expectNil: true,
	}, {
		name: "missing workflow_job field",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "queued",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			// Missing workflow_job
		}),
		expectErr:    true,
		expectErrMsg: "missing workflow_job field",
	}, {
		name: "missing created_at",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "queued",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				"id":     300,
				"labels": []string{"self-hosted"},
				// Missing created_at
			},
		}),
		expectErr:    true,
		expectErrMsg: "missing created_at",
	}, {
		name: "missing started_at for in_progress action",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "in_progress",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				"id":         400,
				"labels":     []string{"self-hosted"},
				"created_at": "2025-01-01T10:00:00Z",
				// Missing started_at
			},
		}),
		expectErr:    true,
		expectErrMsg: "missing started_at",
	}, {
		name: "missing completed_at for completed action",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "completed",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				"id":         500,
				"labels":     []string{"self-hosted"},
				"created_at": "2025-01-01T10:00:00Z",
				"started_at": "2025-01-01T10:05:00Z",
				// Missing completed_at
			},
		}),
		expectErr:    true,
		expectErrMsg: "missing completed_at",
	}, {
		name: "missing job id",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "queued",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				// Missing id
				"labels":     []string{"self-hosted"},
				"created_at": "2025-01-01T10:00:00Z",
			},
		}),
		expectErr:    true,
		expectErrMsg: "missing job id",
	}, {
		name: "missing repository full name",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action":     "queued",
			"repository": map[string]any{
				// Missing full_name
			},
			"workflow_job": map[string]any{
				"id":         600,
				"labels":     []string{"self-hosted"},
				"created_at": "2025-01-01T10:00:00Z",
			},
		}),
		expectErr:    true,
		expectErrMsg: "missing repo full name",
	}, {
		name: "waiting action is ignored",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "waiting",
			"repository": map[string]any{
				"full_name": "canonical/test",
			},
			"workflow_job": map[string]any{
				"id":         700,
				"labels":     []string{"self-hosted"},
				"created_at": "2025-01-01T10:00:00Z",
			},
		}),
		expectNil: true,
	}, {
		name: "in_progress with all fields",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "in_progress",
			"repository": map[string]any{
				"full_name": "canonical/test-repo",
			},
			"workflow_job": map[string]any{
				"id":         800,
				"labels":     []string{"self-hosted", "x64"},
				"status":     "in_progress",
				"created_at": "2025-01-01T10:00:00Z",
				"started_at": "2025-01-01T10:05:00Z",
			},
		}),
		validateJob: func(t *testing.T, job *githubWebhookJob) {
			assert.Equal(t, "800", job.id)
			assert.Equal(t, "in_progress", job.action)
			assert.NotNil(t, job.job.StartedAt)
			assert.Equal(t, "2025-01-01T10:05:00Z", job.job.StartedAt.Format(time.RFC3339))
		},
	}, {
		name: "completed with all fields",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body: mk(map[string]any{
			"action": "completed",
			"repository": map[string]any{
				"full_name": "canonical/test-repo",
			},
			"workflow_job": map[string]any{
				"id":           900,
				"labels":       []string{"self-hosted"},
				"status":       "completed",
				"created_at":   "2025-01-01T10:00:00Z",
				"started_at":   "2025-01-01T10:05:00Z",
				"completed_at": "2025-01-01T10:15:00Z",
			},
		}),
		validateJob: func(t *testing.T, job *githubWebhookJob) {
			assert.Equal(t, "900", job.id)
			assert.Equal(t, "completed", job.action)
			assert.NotNil(t, job.job.CompletedAt)
			assert.Equal(t, "2025-01-01T10:15:00Z", job.job.CompletedAt.Format(time.RFC3339))
		},
	}, {
		name: "invalid JSON body",
		headers: map[string]interface{}{
			"X-GitHub-Event": "workflow_job",
		},
		body:         []byte("{invalid json}"),
		expectErr:    true,
		expectErrMsg: "unable to parse webhook",
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			ctx := context.Background()
			job, err := getWorkflowJob(ctx, tt.headers, tt.body)

			if tt.expectErr {
				assert.Error(t, err)
				if tt.expectErrMsg != "" {
					assert.Contains(t, err.Error(), tt.expectErrMsg)
				}
				assert.Nil(t, job)
			} else if tt.expectNil {
				assert.NoError(t, err)
				assert.Nil(t, job)
			} else {
				assert.NoError(t, err)
				assert.NotNil(t, job)
				if tt.validateJob != nil {
					tt.validateJob(t, job)
				}
			}
		})
	}
}
