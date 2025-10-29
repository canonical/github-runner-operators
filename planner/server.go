/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package planner provides HTTP handlers for the Planner API service.
 */

package planner

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/canonical/github-runner-operators/internal/database"
)

const createFlavorPath = "/api/v1/flavors/"

// FlavorStore is a small interface that matches the relevant method on internal/database.Database.
type FlavorStore interface {
	AddFlavor(ctx context.Context, flavor *database.Flavor) error
}

// Server holds dependencies for the planner HTTP handlers.
type Server struct {
	store           FlavorStore
	OnFlavorCreated func(ctx context.Context, flavor *database.Flavor)
}

// NewServer creates a new Server with the given dependencies.
func NewServer(store FlavorStore) *Server {
	return &Server{store: store}
}

// ServeHTTP routes incoming HTTP requests to the appropriate handler methods.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Path
	switch {
	case strings.HasPrefix(path, createFlavorPath):
		s.createFlavor(w, r)
	default:
		http.NotFound(w, r)
	}
}

// flavorRequest represents the expected JSON payload for creating a flavor.
type flavorRequest struct {
	Platform        string   `json:"platform"`
	Labels          []string `json:"labels"`
	Priority        int      `json:"priority"`
	IsDisabled      bool     `json:"is_disabled"`
	MinimumPressure int      `json:"minimum_pressure"`
}

// createFlavor handles the creation of a new flavor.
func (s *Server) createFlavor(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Extract the flavor name from the URL path.
	flavorName := strings.TrimPrefix(r.URL.Path, createFlavorPath)
	if flavorName == "" {
		http.Error(w, "missing flavor name in URL", http.StatusBadRequest)
		return
	}

	decoder := json.NewDecoder(r.Body)
	defer r.Body.Close()

	req := flavorRequest{}
	if err := decoder.Decode(&req); err != nil {
		http.Error(w, fmt.Sprintf("invalid payload: %v", err), http.StatusBadRequest)
		return
	}

	flavor := &database.Flavor{
		Name:            flavorName,
		Platform:        req.Platform,
		Labels:          req.Labels,
		Priority:        req.Priority,
		IsDisabled:      req.IsDisabled,
		MinimumPressure: req.MinimumPressure,
	}

	err := s.store.AddFlavor(r.Context(), flavor)
	if err == nil {
		if s.OnFlavorCreated != nil {
			s.OnFlavorCreated(r.Context(), flavor)
		}
		w.WriteHeader(http.StatusCreated)
		return
	}
	if err == database.ErrExist {
		http.Error(w, "flavor already exists", http.StatusConflict)
		return
	}
	http.Error(w, fmt.Sprintf("failed to create flavor: %v", err), http.StatusInternalServerError)
}
