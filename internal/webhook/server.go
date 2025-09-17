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
	MsgQueue      queue.Queue
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
		http.Error(w, "Unable to read request body", http.StatusBadRequest)
		return
	}

	if hmac_sha256(body, h.WebhookSecret) != signature {
		http.Error(w, "Invalid signature", http.StatusForbidden)
		return
	}

	err = h.MsgQueue.Push(body)
	if err != nil {
		http.Error(w, "Unable to push to queue", http.StatusInternalServerError)
		return
	}
}

func hmac_sha256(message []byte, secret string) string {
	h := hmac.New(sha256.New, []byte(secret))
	h.Write(message)
	return hex.EncodeToString(h.Sum(nil))
}
