/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package webhook

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net/http"

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

	signature := r.Header.Get(WebhookSignatureHeader)
	if signature == "" {
		http.Error(w, "Missing signature header", http.StatusForbidden)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Unable to read request body", http.StatusInternalServerError)
		return
	}

	if !validateSignature(body, h.WebhookSecret, signature) {
		http.Error(w, "Invalid signature", http.StatusForbidden)
		return
	}

	err = h.Producer.Push(r.Context(), nil, body)
	if err != nil {
		http.Error(w, "Unable to push to queue", http.StatusInternalServerError)
		return
	}
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
