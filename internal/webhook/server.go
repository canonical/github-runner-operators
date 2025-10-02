/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/canonical/mayfly/internal/queue"
)

const WebhookSignatureHeader = "X-Hub-Signature-256"

type Handler struct {
	WebhookSecret string
	Producer      queue.Producer
}

func (h *Handler) Webhook(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 1048576)
	defer r.Body.Close()

	ctx := r.Context()
	signature := r.Header.Get(WebhookSignatureHeader)
	if signature == "" {
		slog.DebugContext(ctx, "missing signature header", "header", r.Header)
		respondWithError(w, r, http.StatusForbidden, "Missing signature header")
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		slog.Error("unable to read request body", "error", err)
		respondWithError(w, r, http.StatusInternalServerError, "unable to read request body")
		return
	}

	if !validateSignature(body, h.WebhookSecret, signature) {
		slog.Debug("invalid signature", "signature", signature)
		respondWithError(w, r, http.StatusForbidden, "Invalid signature")
		return
	}

	err = h.Producer.Push(r.Context(), nil, body)
	if err != nil {
		slog.Error("unable to push message to queue", "error", err)
		respondWithError(w, r, http.StatusInternalServerError, "Unable to push to queue")
		return
	}

	logRequest(r, http.StatusOK, 0)
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

func respondWithError(w http.ResponseWriter, r *http.Request, status int, msg string) {
	http.Error(w, msg, status)
	logRequest(r, status, len(msg))
}

func logRequest(r *http.Request, status int, size int) {
	slog.Info(fmt.Sprintf(
		"%s - - [%s] \"%s %s %s\" %d %d \"%s\"",
		r.RemoteAddr,
		time.Now().Format("02/Jan/2006:15:04:05 -0700"),
		r.Method,
		r.URL.Path,
		r.Proto,
		status,
		size,
		r.UserAgent()))
}
