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

	"github.com/canonical/mayfly/internal/queue"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

const WebhookSignatureHeader = "X-Hub-Signature-256"

type Handler struct {
	WebhookSecret string
	Producer      queue.Producer
}

func (h *Handler) Webhook(w http.ResponseWriter, r *http.Request) {
	requestReceiveTime := time.Now()
	r.Body = http.MaxBytesReader(w, r.Body, 1048576)
	defer r.Body.Close()

	ctx := r.Context()
	ctx, span := trace.Start(ctx, "serve webhook")
	signature := r.Header.Get(WebhookSignatureHeader)
	if signature == "" {
		logger.DebugContext(ctx, "missing signature header", "header", r.Header)
		respondWithError(ctx, w, r, requestReceiveTime, http.StatusForbidden, "Missing signature header")
		inboundWebhookErrors.Add(ctx, 1)
		span.RecordError(errors.New("missing signature header"))
		span.End()
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		logger.ErrorContext(ctx, "unable to read request body", "error", err)
		respondWithError(ctx, w, r, requestReceiveTime, http.StatusInternalServerError, "unable to read request body")
		inboundWebhookErrors.Add(ctx, 1)
		span.RecordError(err)
		span.End()
		return
	}

	if !validateSignature(body, h.WebhookSecret, signature) {
		logger.DebugContext(ctx, "invalid signature", "signature", signature)
		respondWithError(ctx, w, r, requestReceiveTime, http.StatusForbidden, "Invalid signature")
		inboundWebhookErrors.Add(ctx, 1)
		span.RecordError(errors.New("invalid signature"))
		span.End()
		return
	}

	inboundWebhook.Add(ctx, 1)
	span.End()

	ctx, span = trace.Start(ctx, "send webhook")
	traceHeader := make(map[string]string)
	otel.GetTextMapPropagator().Inject(ctx, propagation.MapCarrier(traceHeader))
	rabbitHeaders := make(map[string]interface{})
	for k, v := range traceHeader {
		rabbitHeaders[k] = v
	}
	err = h.Producer.Push(r.Context(), rabbitHeaders, body)
	if err != nil {
		logger.ErrorContext(ctx, "unable to push message to queue", "error", err)
		respondWithError(ctx, w, r, requestReceiveTime, http.StatusInternalServerError, "Unable to push to queue")
		outboundWebhookErrors.Add(ctx, 1)
		span.RecordError(err)
		span.End()
		return
	}
	span.End()

	outboundWebhook.Add(ctx, 1)
	logRequest(ctx, r, requestReceiveTime, http.StatusOK, 0)
}

func validateSignature(message []byte, secret string, signature string) bool {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(message)
	sig, err := hex.DecodeString(signature)
	if err != nil {
		return false
	}
	return hmac.Equal(h.Sum(nil), sig)
}

func respondWithError(ctx context.Context, w http.ResponseWriter, r *http.Request, receiveTime time.Time, status int, msg string) {
	http.Error(w, msg, status)
	logRequest(ctx, r, receiveTime, status, len(msg))
}

func logRequest(ctx context.Context, r *http.Request, receiveTime time.Time, status int, size int) {
	logger.InfoContext(ctx, fmt.Sprintf(
		"%s - - [%s] \"%s %s %s\" %d %d \"%s\"",
		r.RemoteAddr,
		receiveTime.Format("02/Jan/2006:15:04:05 -0700"),
		r.Method,
		r.URL.Path,
		r.Proto,
		status,
		size,
		r.UserAgent()))
}
