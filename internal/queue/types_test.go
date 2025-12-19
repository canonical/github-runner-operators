package queue

import (
	"context"
	"errors"
	"log/slog"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"github.com/stretchr/testify/assert"
	amqp "github.com/rabbitmq/amqp091-go"
)

// fakeChannel implements amqpChannel for unit testing without external deps.
type fakeChannel struct {
	closed      bool
	closeCalls  int
	closeErr    error
	isClosedRet bool

	publishErr     error
	confirmErr     error
	qosErr         error
	consumeErr     error
	declareErr     error
	declarePassErr error

	consumeCh <-chan amqp.Delivery
}

func (f *fakeChannel) PublishWithDeferredConfirm(exchange string, key string, mandatory, immediate bool, msg amqp.Publishing) (confirmation, error) {
	return nil, f.publishErr
}
func (f *fakeChannel) IsClosed() bool { return f.closed || f.isClosedRet }
func (f *fakeChannel) Close() error {
	f.closeCalls++
	f.closed = true
	return f.closeErr
}
func (f *fakeChannel) Confirm(noWait bool) error { return f.confirmErr }
func (f *fakeChannel) QueueDeclare(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return amqp.Queue{Name: name}, f.declareErr
}
func (f *fakeChannel) QueueDeclarePassive(name string, durable, autoDelete, exclusive, noWait bool, args amqp.Table) (amqp.Queue, error) {
	return amqp.Queue{Name: name}, f.declarePassErr
}
func (f *fakeChannel) Consume(queue, consumer string, autoAck, exclusive, noLocal, noWait bool, args amqp.Table) (<-chan amqp.Delivery, error) {
	return f.consumeCh, f.consumeErr
}
func (f *fakeChannel) Qos(prefetchCount, prefetchSize int, global bool) error { return f.qosErr }

// fakeConnection implements amqpConnection for unit testing.
type fakeConnection struct {
	closed      bool
	closeCalls  int
	closeErr    error
	isClosedRet bool

	channel amqpChannel
	chErr   error
}

func (f *fakeConnection) Channel() (amqpChannel, error) { return f.channel, f.chErr }
func (f *fakeConnection) IsClosed() bool                { return f.closed || f.isClosedRet }
func (f *fakeConnection) Close() error {
	f.closeCalls++
	f.closed = true
	return f.closeErr
}

// fakeJobDB implements JobDatabase with no-op methods for consumer tests.
type fakeJobDB struct{}

func (f *fakeJobDB) AddJob(ctx context.Context, job *database.Job) error { return nil }
func (f *fakeJobDB) UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]any) error {
	return nil
}
func (f *fakeJobDB) UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]any) error {
	return nil
}

func TestClient_Close_Table(t *testing.T) {
	chErr := errors.New("channel close failed")
	connErr := errors.New("connection close failed")

	tests := []struct {
		name            string
		client          *Client
		expectErr       error
		expectChCalls   int
		expectConnCalls int
		expectChClosed  bool
		expectConnClose bool
	}{
		{
			name: "both open ok",
			client: &Client{
				amqpChannel:    &fakeChannel{isClosedRet: false},
				amqpConnection: &fakeConnection{isClosedRet: false},
			},
			expectErr:       nil,
			expectChCalls:   1,
			expectConnCalls: 1,
			expectChClosed:  true,
			expectConnClose: true,
		},
		{
			name: "channel error first",
			client: &Client{
				amqpChannel:    &fakeChannel{isClosedRet: false, closeErr: chErr},
				amqpConnection: &fakeConnection{isClosedRet: false, closeErr: connErr},
			},
			expectErr:       chErr,
			expectChCalls:   1,
			expectConnCalls: 1,
		},
		{
			name: "connection error only",
			client: &Client{
				amqpChannel:    &fakeChannel{isClosedRet: false},
				amqpConnection: &fakeConnection{isClosedRet: false, closeErr: connErr},
			},
			expectErr:       connErr,
			expectChCalls:   1,
			expectConnCalls: 1,
			expectChClosed:  true,
			expectConnClose: true,
		},
		{
			name:   "nil resources",
			client: &Client{},
			expectErr:       nil,
			expectChCalls:   0,
			expectConnCalls: 0,
		},
		{
			name: "already closed resources",
			client: &Client{
				amqpChannel:    &fakeChannel{isClosedRet: true},
				amqpConnection: &fakeConnection{isClosedRet: true},
			},
			expectErr:       nil,
			expectChCalls:   0,
			expectConnCalls: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			err := tt.client.Close()
			if tt.expectErr != nil {
				assert.ErrorIs(t, err, tt.expectErr)
			} else {
				assert.NoError(t, err)
			}

			// Inspect internal fakes when present
			if fc, ok := tt.client.amqpChannel.(*fakeChannel); ok {
				assert.Equal(t, tt.expectChCalls, fc.closeCalls)
				if tt.expectChClosed {
					assert.True(t, fc.closed)
				}
			}
			if fconn, ok := tt.client.amqpConnection.(*fakeConnection); ok {
				assert.Equal(t, tt.expectConnCalls, fconn.closeCalls)
				if tt.expectConnClose {
					assert.True(t, fconn.closed)
				}
			}
		})
	}
}

func TestAmqpConsumer_Table(t *testing.T) {
	t.Run("Close delegates to client", func(t *testing.T) {
		t.Parallel()
		ch := &fakeChannel{isClosedRet: false}
		conn := &fakeConnection{isClosedRet: false}

		cons := &AmqpConsumer{
			queueName: "q",
			client: &Client{
				amqpChannel:    ch,
				amqpConnection: conn,
			},
			db:     &fakeJobDB{},
			logger: slog.Default(),
		}

		err := cons.Close()
		assert.NoError(t, err)
		assert.Equal(t, 1, ch.closeCalls)
		assert.Equal(t, 1, conn.closeCalls)
	})

	t.Run("Start exits on context cancellation", func(t *testing.T) {
		t.Parallel()
		msgs := make(chan amqp.Delivery)
		ch := &fakeChannel{isClosedRet: false, consumeCh: msgs}
		conn := &fakeConnection{isClosedRet: false}

		cons := &AmqpConsumer{
			queueName: "test-queue",
			client: &Client{
				amqpChannel:    ch,
				amqpConnection: conn,
			},
			db:     &fakeJobDB{},
			logger: slog.Default(),
		}

		ctx, cancel := context.WithCancel(context.Background())
		errCh := make(chan error, 1)

		go func() { errCh <- cons.Start(ctx) }()
		cancel()

		select {
		case err := <-errCh:
			assert.ErrorIs(t, err, context.Canceled)
		case <-time.After(2 * time.Second):
			t.Fatal("consumer did not exit on context cancellation")
		}
	})
}

func TestClient_Close_Idempotent(t *testing.T) {
	ch := &fakeChannel{isClosedRet: false}
	conn := &fakeConnection{isClosedRet: false}

	c := &Client{
		amqpChannel:    ch,
		amqpConnection: conn,
	}

	// First close should close both
	err := c.Close()
	assert.NoError(t, err)
	assert.Equal(t, 1, ch.closeCalls)
	assert.Equal(t, 1, conn.closeCalls)

	// Second close should be a no-op
	err = c.Close()
	assert.NoError(t, err)
	assert.Equal(t, 1, ch.closeCalls)
	assert.Equal(t, 1, conn.closeCalls)
}
