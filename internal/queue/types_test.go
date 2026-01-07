package queue

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/stretchr/testify/assert"
)

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
	/*
		arrange: Setup test error scenarios and expected outcomes.
		act: Close the client.
		assert: Check error and verify close calls.
	*/
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
				amqpChannel:    &MockAmqpChannel{isClosedRet: false},
				amqpConnection: &MockAmqpConnection{isClosedRet: false},
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
				amqpChannel:    &MockAmqpChannel{isClosedRet: false, closeErr: chErr},
				amqpConnection: &MockAmqpConnection{isClosedRet: false, closeErr: connErr},
			},
			expectErr:       chErr,
			expectChCalls:   1,
			expectConnCalls: 1,
		},
		{
			name: "connection error only",
			client: &Client{
				amqpChannel:    &MockAmqpChannel{isClosedRet: false},
				amqpConnection: &MockAmqpConnection{isClosedRet: false, closeErr: connErr},
			},
			expectErr:       connErr,
			expectChCalls:   1,
			expectConnCalls: 1,
			expectChClosed:  true,
			expectConnClose: true,
		},
		{
			name:            "nil resources",
			client:          &Client{},
			expectErr:       nil,
			expectChCalls:   0,
			expectConnCalls: 0,
		},
		{
			name: "already closed resources",
			client: &Client{
				amqpChannel:    &MockAmqpChannel{isClosedRet: true},
				amqpConnection: &MockAmqpConnection{isClosedRet: true},
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

			if fc, ok := tt.client.amqpChannel.(*MockAmqpChannel); ok {
				assert.Equal(t, tt.expectChCalls, fc.closeCalls)
				if tt.expectChClosed {
					assert.True(t, fc.isclosed)
				}
			}
			if fconn, ok := tt.client.amqpConnection.(*MockAmqpConnection); ok {
				assert.Equal(t, tt.expectConnCalls, fconn.closeCalls)
				if tt.expectConnClose {
					assert.True(t, fconn.isclosed)
				}
			}
		})
	}
}

func TestAmqpConsumer_Table(t *testing.T) {
	t.Run("Close delegates to client", func(t *testing.T) {
		t.Parallel()
		/*
			arrange: Setup fake channel and connection.
			act: Close the consumer.
			assert: Check no error and verify close calls.
		*/
		ch := &MockAmqpChannel{isClosedRet: false}
		conn := &MockAmqpConnection{isClosedRet: false}

		cons := &AmqpConsumer{
			client: &Client{
				amqpChannel:    ch,
				amqpConnection: conn,
			},
			channel: make(<-chan amqp.Delivery),
		}

		err := cons.Close()
		assert.NoError(t, err)
		assert.Equal(t, 1, ch.closeCalls)
		assert.Equal(t, 1, conn.closeCalls)
	})
}

func TestClient_Close_Idempotent(t *testing.T) {
	/*
		arrange: Setup client with open channel and connection.
		act: Close the client twice.
		assert: First close should close both, second close should be a no-op.
	*/
	ch := &MockAmqpChannel{isClosedRet: false}
	conn := &MockAmqpConnection{isClosedRet: false}

	c := &Client{
		amqpChannel:    ch,
		amqpConnection: conn,
	}

	err := c.Close()
	assert.NoError(t, err)
	assert.Equal(t, 1, ch.closeCalls)
	assert.Equal(t, 1, conn.closeCalls)

	err = c.Close()
	assert.NoError(t, err)
	assert.Equal(t, 1, ch.closeCalls)
	assert.Equal(t, 1, conn.closeCalls)
}

func TestDeclareQueueWithDeadLetter(t *testing.T) {
	/*
		arrange: Create a client with mock channel.
		act: Call declareQueueWithDeadLetter.
		assert: Queue is declared with x-dead-letter-exchange argument.
	*/
	ch := &MockAmqpChannel{}
	client := &Client{amqpChannel: ch}

	err := client.declareQueueWithDeadLetter("test-queue", "test-dlx")

	assert.NoError(t, err)
	assert.Equal(t, "test-queue", ch.queueName)
	assert.True(t, ch.queueDurable)
	assert.Equal(t, "test-dlx", ch.queueArgs["x-dead-letter-exchange"])
}

func TestDeclareQueueWithDeadLetterError(t *testing.T) {
	/*
		arrange: Create a client with mock channel that returns error.
		act: Call declareQueueWithDeadLetter.
		assert: Error is returned.
	*/
	ch := &MockAmqpChannel{queueDeclareError: true}
	client := &Client{amqpChannel: ch}

	err := client.declareQueueWithDeadLetter("test-queue", "test-dlx")

	assert.Error(t, err)
	assert.ErrorContains(t, err, "failed to declare AMQP queue with dead-letter")
}
