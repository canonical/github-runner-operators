/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Unit tests for the consumer.
 */

package queue

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"maps"
	"sync/atomic"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
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

type fakeConn struct {
	closed        bool
	channelErr    error
	channel       *fakeChan
	channelCalled int32
}

func (c *fakeConn) Channel() (amqpChannel, error) {
	atomic.AddInt32(&c.channelCalled, 1)
	if c.channelErr != nil {
		return nil, c.channelErr
	}
	return c.channel, nil
}

func (c *fakeConn) IsClosed() bool { return c.closed }
func (c *fakeConn) Close() error {
	c.closed = true
	return nil
}

type fakeChan struct {
	closed          bool
	confirmErr      error
	queueDeclareErr error
	consumeErr      error
	deliveries      <-chan amqp.Delivery
}

func (ch *fakeChan) PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (confirmation, error) {
	return nil, errors.New("not implemented in fake")
}

func (ch *fakeChan) IsClosed() bool            { return ch.closed }
func (ch *fakeChan) Confirm(noWait bool) error { return ch.confirmErr }

func (ch *fakeChan) QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return amqp.Queue{}, nil
}

func (ch *fakeChan) QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	if ch.queueDeclareErr != nil {
		return amqp.Queue{}, ch.queueDeclareErr
	}
	return amqp.Queue{Name: name}, nil
}

func (ch *fakeChan) Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error) {
	if ch.consumeErr != nil {
		return nil, ch.consumeErr
	}
	return ch.deliveries, nil
}

func (ch *fakeChan) Qos(prefetchCount, prefetchSize int, global bool) error {
	return nil
}

func (ch *fakeChan) Close() error {
	ch.closed = true
	return nil
}

func TestConsumer(t *testing.T) {
	mk := func(m map[string]any) []byte { b, _ := json.Marshal(m); return b }
	tests := []struct {
		name                                string
		setupDB                             func(*fakeDB)
		deliveries                          func() <-chan amqp.Delivery
		confirmErr, qDeclareErr, consumeErr error
		expectErrSub                        string
		checkDB                             func(*testing.T, *fakeDB)
	}{{
		name:    "succeeds when queued job is inserted",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "queued",
					"workflow_job": map[string]any{
						"id":         1,
						"labels":     []string{"linux"},
						"status":     "queued",
						"created_at": "2025-01-01T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:1"], "job not inserted")
		},
	}, {
		name: "skips insert when queued job already exists",
		setupDB: func(db *fakeDB) {
			db.jobs["github:2"] = &database.Job{ID: "2", Platform: "github"}
		},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "queued",
					"workflow_job": map[string]any{
						"id":         2,
						"labels":     []string{"x"},
						"status":     "queued",
						"created_at": "2025-01-01T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:2"], "job not found")
		},
	}, {
		name: "succeeds when job updated to in_progress",
		setupDB: func(db *fakeDB) {
			db.jobs["github:3"] = &database.Job{ID: "3", Platform: "github", Raw: map[string]any{}}
		},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "in_progress",
					"workflow_job": map[string]any{
						"id":         3,
						"labels":     []string{},
						"status":     "in_progress",
						"started_at": "2025-01-02T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:3"], "job not found")
			assert.NotNil(t, db.jobs["github:3"].StartedAt, "started_at not set")
			assert.Equal(t, "2025-01-02T00:00:00Z", db.jobs["github:3"].StartedAt.Format(time.RFC3339), "started_at incorrect")
		},
	}, {
		name:    "insert and update when job not found on start",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "in_progress",
					"workflow_job": map[string]any{
						"id":         21,
						"labels":     []string{},
						"status":     "in_progress",
						"created_at": "2025-01-01T00:00:00Z",
						"started_at": "2025-01-02T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:21"], "job should be created on start when missing")
			assert.NotNil(t, db.jobs["github:21"].StartedAt, "started_at not set")
		},
	}, {
		name: "succeeds when job updated to completed",
		setupDB: func(db *fakeDB) {
			db.jobs["github:5"] = &database.Job{ID: "5", Platform: "github"}
		},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "completed",
					"workflow_job": map[string]any{
						"id":           5,
						"labels":       []string{},
						"status":       "completed",
						"completed_at": "2025-01-03T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:5"], "job not found")
			assert.NotNil(t, db.jobs["github:5"].CompletedAt, "completed_at not set")
			assert.Equal(t, "2025-01-03T00:00:00Z", db.jobs["github:5"].CompletedAt.Format(time.RFC3339), "completed_at incorrect")
		},
	}, {
		name:    "skips when JSON is invalid",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body:    []byte("{not-json}"),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
	}, {
		name:    "ignores when action is unknown",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "unknown",
					"workflow_job": map[string]any{
						"id":         16,
						"labels":     []string{"l"},
						"status":     "queued",
						"created_at": "2025-01-01T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:16"], "job should not be inserted")
		},
	}, {
		name:    "fail when queue declare failure",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			return make(chan amqp.Delivery)
		},
		qDeclareErr:  errors.New("queue declare fail"),
		expectErrSub: "failed to declare AMQP queue: queue declare fail",
	}, {
		name:         "fail when consume failure",
		setupDB:      func(db *fakeDB) {},
		deliveries:   func() <-chan amqp.Delivery { return nil },
		consumeErr:   errors.New("consume fail"),
		expectErrSub: "failed to consume message: consume fail",
	}, {
		name:    "requeues when AddJob fails with other error",
		setupDB: func(db *fakeDB) { db.addErr = errors.New("db down") },
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "queued",
					"workflow_job": map[string]any{
						"id":         10,
						"labels":     []string{"l"},
						"status":     "queued",
						"created_at": "2025-01-01T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:10"], "job should not be inserted")
		},
	}, {
		name:    "fails when started_at is invalid",
		setupDB: func(db *fakeDB) { db.jobs["github:11"] = &database.Job{ID: "11", Platform: "github"} },
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "in_progress",
					"workflow_job": map[string]any{
						"id":         11,
						"labels":     []string{},
						"status":     "in_progress",
						"started_at": "invalid",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			j := db.jobs["github:11"]
			assert.NotNil(t, j, "job should exist")
			assert.Nil(t, j.StartedAt, "started_at should not be set on invalid time")
		},
	}, {
		name:    "fails when completed_at is invalid",
		setupDB: func(db *fakeDB) { db.jobs["github:12"] = &database.Job{ID: "12", Platform: "github"} },
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "completed",
					"workflow_job": map[string]any{
						"id":           12,
						"labels":       []string{},
						"status":       "completed",
						"completed_at": "invalid",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			j := db.jobs["github:12"]
			assert.NotNil(t, j, "job should exist")
			assert.Nil(t, j.CompletedAt, "completed_at should not be set on invalid time")
		},
	}, {
		name:    "insert and update when job not found on completion",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "workflow_job"},
				Body: mk(map[string]any{
					"action": "completed",
					"workflow_job": map[string]any{
						"id":           22,
						"labels":       []string{},
						"status":       "completed",
						"created_at":   "2025-01-01T00:00:00Z",
						"started_at":   "2025-01-02T00:00:00Z",
						"completed_at": "2025-01-03T00:00:00Z",
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.NotNil(t, db.jobs["github:22"], "job should be created on completion when missing")
			assert.NotNil(t, db.jobs["github:22"].CompletedAt, "completed_at not set")
			assert.Equal(t, "2025-01-03T00:00:00Z", db.jobs["github:22"].CompletedAt.Format(time.RFC3339), "completed_at incorrect")
		},
	}, {
		name:    "discards message when X-GitHub-Event header is missing",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
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
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Nil(t, db.jobs["github:23"], "job should not be inserted when header is missing")
		},
	}, {
		name:    "discards non-workflow_job events",
		setupDB: func(db *fakeDB) {},
		deliveries: func() <-chan amqp.Delivery {
			ch := make(chan amqp.Delivery, 1)
			ch <- amqp.Delivery{
				Headers: amqp.Table{"X-GitHub-Event": "pull_request"},
				Body: mk(map[string]any{
					"action": "opened",
					"pull_request": map[string]any{
						"id": 24,
					},
				}),
			}
			close(ch)
			return ch
		},
		expectErrSub: "context canceled",
		checkDB: func(t *testing.T, db *fakeDB) {
			assert.Empty(t, db.jobs, "no jobs should be inserted for non-workflow_job events")
		},
	}}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			db := newFakeDB()
			tt.setupDB(db)
			fch := &fakeChan{deliveries: nil, confirmErr: tt.confirmErr, queueDeclareErr: tt.qDeclareErr, consumeErr: tt.consumeErr}
			if tt.deliveries != nil {
				fch.deliveries = tt.deliveries()
			}
			fconn := &fakeConn{channel: fch}

			consumer := &AmqpConsumer{
				client: &Client{
					uri:         "amqp://x",
					connectFunc: func(uri string) (amqpConnection, error) { return fconn, nil }},
				queueName: "queue-x",
				db:        db,
				logger:    slog.Default(),
			}

			ctx, cancel := context.WithCancel(context.Background())
			go func() {
				time.Sleep(100 * time.Millisecond)
				cancel() // Cancel immediately after Start to end the test
			}()

			err := consumer.Start(ctx)

			assert.ErrorContains(t, err, tt.expectErrSub, "expected error containing %q, got %v", tt.expectErrSub, err)
			if tt.checkDB != nil {
				tt.checkDB(t, db)
			}
		})
	}
}
