/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

// Package github provides shared constants for GitHub webhook integration.
package github

const (
	SignatureHeader                  = "X-Hub-Signature-256"
	EventHeader                      = "X-GitHub-Event"
	HookIDHeader                     = "X-GitHub-Hook-ID"
	DeliveryHeader                   = "X-GitHub-Delivery"
	HookInstallationTargetTypeHeader = "X-GitHub-Hook-Installation-Target-Type"
	HookInstallationTargetIDHeader   = "X-GitHub-Hook-Installation-Target-ID"
	SignaturePrefix                  = "sha256="
)
