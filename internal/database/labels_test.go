/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package database

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

// stripDefaultLabels normalizes labels to lowercase and removes GitHub's
// implicit labels case-insensitively, so flavor matching is unaffected by the
// casing GitHub uses for the architecture/OS labels it injects.
func TestStripDefaultLabels(t *testing.T) {
	tests := []struct {
		name   string
		labels []string
		want   []string
	}{{
		name:   "lowercases mixed-case labels",
		labels: []string{"X64", "Large", "Noble"},
		want:   []string{"x64", "large", "noble"},
	}, {
		name:   "strips default labels regardless of casing",
		labels: []string{"Self-Hosted", "Linux", "X64"},
		want:   []string{"x64"},
	}, {
		name:   "strips already-lowercase default labels",
		labels: []string{"self-hosted", "linux", "amd64"},
		want:   []string{"amd64"},
	}, {
		name:   "returns empty for only default labels",
		labels: []string{"self-hosted", "LINUX"},
		want:   []string{},
	}, {
		name:   "handles empty input",
		labels: []string{},
		want:   []string{},
	}}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			assert.Equal(t, tc.want, stripDefaultLabels(tc.labels))
		})
	}
}
