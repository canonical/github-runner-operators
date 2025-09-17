/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package webhook

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
)

const webhookPath = "/webhook"
const payload = `{"message":"Hello, Alice!"}`
const secret = "fake-secret"
const valid_signature_header = "0aca2d7154cddad4f56f246cad61f1485df34b8056e10c4e4799494376fb3413" // HMAC SHA256 of body with secret "fake-secret"

type FakeQueue struct {
	Messages [][]byte
}

func (q *FakeQueue) Push(msg []byte) error {
	q.Messages = append(q.Messages, msg)
	return nil
}

type ErrorQueue struct{}

func (q *ErrorQueue) Push(msg []byte) error {
	return fmt.Errorf("queue error")
}

func TestWebhookForwarded(t *testing.T) {
	/*
		arrange: create request with valid signature header
		act: call WebhookHandler
		assert: status 200, message was forwarded to queue
	*/

	req := setupRequest()
	fakeQueue := &FakeQueue{}
	handler := Handler{
		WebhookSecret: secret,
		MsgQueue:      fakeQueue,
	}
	w := httptest.NewRecorder()
	handler.Webhook(w, req)
	res := w.Result()
	defer res.Body.Close()

	assert.Equal(t, http.StatusOK, res.StatusCode, "expected status 200 got %v", res.Status)
	assert.NotNil(t, fakeQueue.Messages, "expected messages in queue")
	assert.Equal(t, 1, len(fakeQueue.Messages), "expected 1 message in queue")
	assert.Equal(t, payload, string(fakeQueue.Messages[0]), "expected message body to match")

}

func setupRequest() *http.Request {
	req := httptest.NewRequest(http.MethodPost, webhookPath, strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set(WebhookSignatureHeader, valid_signature_header)

	return req
}

func TestWebhookQueueError(t *testing.T) {
	/*
		arrange: create request with valid signature header and a queue that returns an error
		act: call WebhookHandler
		assert: status 500
	*/
	req := setupRequest()
	w := httptest.NewRecorder()
	errQueue := &ErrorQueue{}

	handler := Handler{
		WebhookSecret: secret,
		MsgQueue:      errQueue,
	}
	handler.Webhook(w, req)
	res := w.Result()
	defer res.Body.Close()

	assert.Equal(t, http.StatusInternalServerError, res.StatusCode, "expected status 500 got %v", res.Status)
}

func TestWebhookMissingSignatureHeader(t *testing.T) {
	/*
		arrange: create request without signature header
		act: call WebhookHandler
		assert: status 403
	*/
	req := setupRequest()
	req.Header.Del(WebhookSignatureHeader)
	w := httptest.NewRecorder()

	handler := Handler{
		WebhookSecret: secret,
		MsgQueue:      &FakeQueue{},
	}
	handler.Webhook(w, req)
	res := w.Result()
	defer res.Body.Close()

	assert.Equal(t, http.StatusForbidden, res.StatusCode, "expected status 403 got %v", res.Status)
}

func TestWebhookInvalidSignature(t *testing.T) {
	/*
		arrange: create request with invalid signature header
		act: call WebhookHandler
		assert: status 403
	*/
	req := setupRequest()
	invalidSignatureHeader := "0aca2d7154cinvalid56f246cad61f1485df34b8056e10c4e4799494376fb3412"
	req.Header.Set(WebhookSignatureHeader, invalidSignatureHeader)
	w := httptest.NewRecorder()

	handler := Handler{
		WebhookSecret: secret,
		MsgQueue:      &FakeQueue{},
	}
	handler.Webhook(w, req)
	res := w.Result()
	defer res.Body.Close()

	assert.Equal(t, http.StatusForbidden, res.StatusCode, "expected status 403 got %v", res.Status)
	assert.NotNil(t, res.Body, "expected response body")
	respBody, _ := io.ReadAll(res.Body)
	assert.Contains(t, string(respBody), "Invalid signature")
}
