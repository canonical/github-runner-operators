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
	"strings"

	"github.com/canonical/github-runner-operators/internal/database"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const (
	createFlavorPattern      = "/api/v1/flavors/{name}"
	getFlavorPressurePattern = "/api/v1/flavors/{name}/pressure"
	createAuthTokenPattern   = "/api/v1/auth/token/{name}"
	deleteAuthTokenPattern   = "/api/v1/auth/token/{name}"
	healthPattern            = "/health"
	allFlavorName            = "_"
	flavorPlatform           = "github" // Currently only github is supported
)

// FlavorStore is a small interface that matches the relevant method on internal/database.Database.
type FlavorStore interface {
	AddFlavor(ctx context.Context, flavor *database.Flavor) error
	ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error)
	GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error)
}

// AuthStore provides methods to manage general authentication tokens in the DB.
type AuthStore interface {
	CreateAuthToken(ctx context.Context, name string) ([32]byte, error)
	DeleteAuthToken(ctx context.Context, name string) error
}

// Server holds dependencies for the planner HTTP handlers.
type Server struct {
	metrics *Metrics
	mux     *http.ServeMux
	store   FlavorStore
	auth    AuthStore
	// adminToken is the bootstrap token used to manage general tokens. It is not stored in DB.
	adminToken string
}

// NewServer creates a new Server with the given dependencies.
func NewServer(store FlavorStore, auth AuthStore, metrics *Metrics, adminToken string) *Server {
	s := &Server{store: store, auth: auth, adminToken: adminToken, mux: http.NewServeMux(), metrics: metrics}

	// Register routes
	s.mux.Handle("POST "+createFlavorPattern, otelhttp.WithRouteTag(createFlavorPattern, http.HandlerFunc(s.createFlavor)))
	s.mux.Handle("GET "+getFlavorPressurePattern, otelhttp.WithRouteTag(getFlavorPressurePattern, http.HandlerFunc(s.getFlavorPressure)))
	s.mux.Handle("POST "+createAuthTokenPattern, otelhttp.WithRouteTag(createAuthTokenPattern, s.adminProtected(http.HandlerFunc(s.createAuthToken))))
	s.mux.Handle("DELETE "+deleteAuthTokenPattern, otelhttp.WithRouteTag(deleteAuthTokenPattern, s.adminProtected(http.HandlerFunc(s.deleteAuthToken))))
	s.mux.Handle("GET "+healthPattern, otelhttp.WithRouteTag(healthPattern, http.HandlerFunc(s.health)))

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

// getFlavorPressure handles retrieving the pressure for a specific or all flavors.
func (s *Server) getFlavorPressure(w http.ResponseWriter, r *http.Request) {
	var pressures = map[string]int{}
	var err error

	flavorName := r.PathValue("name")
	switch flavorName {
	case allFlavorName:
		pressures, err = s.store.GetPressures(r.Context(), flavorPlatform)
	default:
		pressures, err = s.store.GetPressures(r.Context(), flavorPlatform, flavorName)
	}

	if err != nil {
		http.Error(w, fmt.Sprintf("failed to get flavor pressure: %v", err), http.StatusInternalServerError)
		return
	}

	if len(pressures) == 0 {
		http.Error(w, "flavor not found", http.StatusNotFound)
		return
	}

	respondWithJSON(w, http.StatusOK, pressures)
}

// health handles health check requests.
func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	respondWithJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// adminProtected enforces admin token authentication for sensitive routes.
func (s *Server) adminProtected(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authz := r.Header.Get("Authorization")
		parts := strings.SplitN(authz, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
			http.Error(w, "invalid authorization header", http.StatusBadRequest)
			return
		}
		if parts[1] != s.adminToken {
			w.Header().Set("WWW-Authenticate", "Bearer")
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

type tokenResponse struct {
	Name  string `json:"name"`
	Token string `json:"token"`
}

// createAuthToken handles creation of a general authentication token (admin-protected).
func (s *Server) createAuthToken(w http.ResponseWriter, r *http.Request) {
	if s.auth == nil {
		http.Error(w, "auth store not configured", http.StatusInternalServerError)
		return
	}
	name := r.PathValue("name")
	if name == "" {
		http.Error(w, "missing token name", http.StatusBadRequest)
		return
	}
	token, err := s.auth.CreateAuthToken(r.Context(), name)
	if err == nil {
		// Return token as a base64url (no padding) string
		// Avoid logging or persisting plaintext token beyond this response.
		enc := base64RawURLEncode(token[:])
		respondWithJSON(w, http.StatusCreated, tokenResponse{Name: name, Token: enc})
		return
	}
	if errors.Is(err, database.ErrExist) {
		http.Error(w, "token already exists", http.StatusConflict)
		return
	}
	http.Error(w, fmt.Sprintf("failed to create token: %v", err), http.StatusInternalServerError)
}

// deleteAuthToken handles deletion of a general authentication token (admin-protected).
func (s *Server) deleteAuthToken(w http.ResponseWriter, r *http.Request) {
	if s.auth == nil {
		http.Error(w, "auth store not configured", http.StatusInternalServerError)
		return
	}
	name := r.PathValue("name")
	if name == "" {
		http.Error(w, "missing token name", http.StatusBadRequest)
		return
	}
	if err := s.auth.DeleteAuthToken(r.Context(), name); err != nil {
		http.Error(w, fmt.Sprintf("failed to delete token: %v", err), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// respondWithJSON sends a JSON response with the given status code and payload.
func respondWithJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(payload)
}

// base64RawURLEncode encodes bytes using RawURLEncoding without padding.
func base64RawURLEncode(b []byte) string {
	// Use a local wrapper to avoid importing encoding/base64 at top-level without name collision.
	// This function keeps import list tidy when reading diffs.
	return base64RawURLEncodeImpl(b)
}
