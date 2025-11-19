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
	"errors"
	"fmt"
	"net/http"

	"github.com/canonical/github-runner-operators/internal/database"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const createFlavorPattern = "/api/v1/flavors/{name}"

// FlavorStore is a small interface that matches the relevant method on internal/database.Database.
type FlavorStore interface {
	AddFlavor(ctx context.Context, flavor *database.Flavor) error
	ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error)
	GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error)
}

// Server holds dependencies for the planner HTTP handlers.
type Server struct {
	metrics *Metrics
	mux     *http.ServeMux
	store   FlavorStore
}

// NewServer creates a new Server with the given dependencies.
func NewServer(store FlavorStore, metrics *Metrics) *Server {
	s := &Server{store: store, mux: http.NewServeMux(), metrics: metrics}

	// Register routes
	s.mux.Handle("POST "+createFlavorPattern, otelhttp.WithRouteTag(createFlavorPattern, http.HandlerFunc(s.createFlavor)))

	return s
}

// ServeHTTP routes incoming HTTP requests to the appropriate handler methods.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mux.ServeHTTP(w, r)
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
	decoder := json.NewDecoder(r.Body)
	defer r.Body.Close()

	req := flavorRequest{}
	if err := decoder.Decode(&req); err != nil {
		http.Error(w, fmt.Sprintf("invalid payload: %v", err), http.StatusBadRequest)
		return
	}

	flavorName := r.PathValue("name")
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
		w.WriteHeader(http.StatusCreated)
		return
	}

	if errors.Is(err, database.ErrExist) {
		http.Error(w, "flavor already exists", http.StatusConflict)
		return
	}

	http.Error(w, fmt.Sprintf("failed to create flavor: %v", err), http.StatusInternalServerError)
}
