/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package webhook

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/canonical/github-runner-operators/internal/queue"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

const (
	WebhookSignatureHeader = "X-Hub-Signature-256"
	bodyLimit              = 1048576
	WebhookSignaturePrefix = "sha256="
)

type httpError struct {
	code    int
	message string
	err     error
}

func (e *httpError) Error() string {
	if e.err != nil {
		return fmt.Sprintf("%s: %v", e.message, e.err)
	}
	return e.message
}

func (e *httpError) Unwrap() error {
	return e.err
}

type Handler struct {
	WebhookSecret string
	Producer      queue.Producer
}

func (h *Handler) receiveWebhook(ctx context.Context, r *http.Request) ([]byte, error) {
	reader := io.LimitReader(r.Body, bodyLimit+1)
	signature := r.Header.Get(WebhookSignatureHeader)
	if signature == "" {
		logger.DebugContext(ctx, "missing signature header", "header", r.Header)
		return nil, &httpError{code: http.StatusForbidden, message: "missing signature header"}
	}
	body, err := io.ReadAll(reader)
	if err != nil {
		logger.ErrorContext(ctx, "unable to read request body", "error", err)
		return nil, &httpError{code: http.StatusInternalServerError, message: "unable to read request body", err: err}
	}
	if len(body) > bodyLimit {
		logger.ErrorContext(ctx, "body exceeds limit")
		return nil, &httpError{code: http.StatusBadRequest, message: "body length exceeds limit"}
	}
	if !validateSignature(body, h.WebhookSecret, signature) {
		logger.DebugContext(ctx, "invalid signature", "signature", signature)
		return nil, &httpError{code: http.StatusForbidden, message: "webhook contains invalid signature"}
	}
	return body, nil
}

func (h *Handler) sendWebhook(ctx context.Context, body []byte) error {
	header := make(map[string]string)
	otel.GetTextMapPropagator().Inject(ctx, propagation.MapCarrier(header))
	rabbitHeaders := make(map[string]interface{})
	for k, v := range header {
		rabbitHeaders[k] = v
	}
	err := h.Producer.Push(ctx, rabbitHeaders, body)
	if err != nil {
		return fmt.Errorf("failed to send webhook: %v", err)
	}
	return nil
}

func (h *Handler) serveHTTP(ctx context.Context, r *http.Request) error {
	defer func() {
		if err := r.Body.Close(); err != nil {
			logger.ErrorContext(ctx, "failed to close request body", "error", err)
		}
	}()
	ctx, span := trace.Start(ctx, "serve webhook")
	webhook, err := h.receiveWebhook(ctx, r)
	if err != nil {
		inboundWebhookErrors.Add(ctx, 1)
		span.RecordError(err)
		span.End()
		return err
	} else {
		inboundWebhook.Add(ctx, 1)
		span.End()
	}

	ctx, span = trace.Start(ctx, "send webhook")
	err = h.sendWebhook(ctx, webhook)
	if err != nil {
		outboundWebhookErrors.Add(ctx, 1)
		span.RecordError(err)
		span.End()
		return err
	} else {
		outboundWebhook.Add(ctx, 1)
		span.End()
	}
	return nil
}

func (h *Handler) Webhook(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	receiveTime := time.Now()

	err := h.serveHTTP(ctx, r)
	status := http.StatusOK
	message := ""
	if err != nil {
		var he *httpError
		if errors.As(err, &he) {
			status = he.code
			message = he.message
		} else {
			status = http.StatusInternalServerError
		}
	}
	w.WriteHeader(status)
	n, err := w.Write([]byte(message))
	if err != nil {
		logger.ErrorContext(ctx, "failed to write response", "error", err)
	}
	logger.InfoContext(ctx, fmt.Sprintf(
		"%s - - [%s] \"%s %s %s\" %d %d \"%s\"",
		r.RemoteAddr,
		receiveTime.Format("02/Jan/2006:15:04:05 -0700"),
		r.Method,
		r.URL.Path,
		r.Proto,
		status,
		n,
		r.UserAgent()))
}

func validateSignature(message []byte, secret string, signature string) bool {
	if len(signature) < len(WebhookSignaturePrefix) {
		return false
	}
	signature_without_prefix := signature[len(WebhookSignaturePrefix):]
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(message)
	sig, err := hex.DecodeString(signature_without_prefix)
	if err != nil {
		return false
	}
	return hmac.Equal(h.Sum(nil), sig)
}
