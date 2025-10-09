/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package webhook

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/canonical/mayfly/internal/telemetry"
	"github.com/stretchr/testify/assert"
)

const webhookPath = "/webhook"
const payload = `{"message":"Hello, Alice!"}`
const secret = "fake-secret"
const valid_signature_header = "0aca2d7154cddad4f56f246cad61f1485df34b8056e10c4e4799494376fb3413" // HMAC SHA256 of body with secret "fake-secret"

type FakeProducer struct {
	Messages [][]byte
}

func (q *FakeProducer) Push(_ context.Context, _ map[string]interface{}, msg []byte) error {
	q.Messages = append(q.Messages, msg)
	return nil
}

type ErrorProducer struct{}

func (q *ErrorProducer) Push(_ context.Context, _ map[string]interface{}, _ []byte) error {
	return fmt.Errorf("queue error")
}

func TestWebhookForwarded(t *testing.T) {
	/*
		arrange: create request with valid signature header
		act: call WebhookHandler
		assert: status 200, message was forwarded to queue
	*/
	mr := telemetry.InitTestMetricReader(t)
	req := setupRequest()
	fakeProducer := &FakeProducer{}
	handler := Handler{
		WebhookSecret: secret,
		Producer:      fakeProducer,
	}
	w := httptest.NewRecorder()
	handler.Webhook(w, req)
	res := w.Result()
	defer res.Body.Close()

	assert.Equal(t, http.StatusOK, res.StatusCode, "expected status 200 got %v", res.Status)
	assert.NotNil(t, fakeProducer.Messages, "expected messages in queue")
	assert.Equal(t, 1, len(fakeProducer.Messages), "expected 1 message in queue")
	assert.Equal(t, payload, string(fakeProducer.Messages[0]), "expected message body to match")
	m := mr.Collect(t)
	assert.Equal(t, 1.0, m.Counter(t, "mayfly.webhook.gateway.inbound"))
	assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.inbound.errors"))
	assert.Equal(t, 1.0, m.Counter(t, "mayfly.webhook.gateway.outbound"))
	assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.outbound.errors"))
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
	mr := telemetry.InitTestMetricReader(t)
	req := setupRequest()
	w := httptest.NewRecorder()
	errProducer := &ErrorProducer{}

	handler := Handler{
		WebhookSecret: secret,
		Producer:      errProducer,
	}
	handler.Webhook(w, req)
	res := w.Result()
	defer res.Body.Close()

	m := mr.Collect(t)
	assert.Equal(t, http.StatusInternalServerError, res.StatusCode, "expected status 500 got %v", res.Status)
	assert.Equal(t, 1.0, m.Counter(t, "mayfly.webhook.gateway.inbound"))
	assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.inbound.errors"))
	assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.outbound"))
	assert.Equal(t, 1.0, m.Counter(t, "mayfly.webhook.gateway.outbound.errors"))
}

func TestWebhookInvalidSignature(t *testing.T) {
	/*
		arrange: create invalid signature test cases
		act: call webhook handler
		assert: A 403 response is returned
	*/
	tests := []struct {
		name                    string
		signature               string
		expectedResponseMessage string
	}{
		{
			name:                    "Invalid Signature",
			signature:               "0aca2d7154cinvalid56f246cad61f1485df34b8056e10c4e4799494376fb3412",
			expectedResponseMessage: "Invalid signature",
		},
		{
			name:                    "Non ASCII Signature",
			signature:               "非ASCII签名",
			expectedResponseMessage: "Invalid signature",
		},
		{
			name:                    "Empty Signature",
			signature:               "",
			expectedResponseMessage: "Missing signature header",
		},
		{
			name:                    "Missing Signature Header",
			signature:               "",
			expectedResponseMessage: "Missing signature header",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mr := telemetry.InitTestMetricReader(t)
			req := setupRequest()
			if tt.name == "Missing Signature Header" {
				req.Header.Del(WebhookSignatureHeader)
			} else {
				req.Header.Set(WebhookSignatureHeader, tt.signature)
			}
			w := httptest.NewRecorder()

			fakeProducer := &FakeProducer{}
			handler := Handler{
				WebhookSecret: secret,
				Producer:      fakeProducer,
			}
			handler.Webhook(w, req)
			res := w.Result()
			defer res.Body.Close()

			assert.Equal(t, http.StatusForbidden, res.StatusCode, "expected status %v got %v", http.StatusForbidden, res.Status)
			assert.NotNil(t, res.Body, "expected response body")
			respBody, _ := io.ReadAll(res.Body)
			assert.Contains(t, string(respBody), tt.expectedResponseMessage)
			assert.Equal(t, 0, len(fakeProducer.Messages), "expected 0 message in queue")

			m := mr.Collect(t)
			assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.inbound"))
			assert.Equal(t, 1.0, m.Counter(t, "mayfly.webhook.gateway.inbound.errors"))
			assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.outbound"))
			assert.Equal(t, 0.0, m.Counter(t, "mayfly.webhook.gateway.outbound.errors"))
		})
	}
}
