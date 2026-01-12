/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package planner provides HTTP handlers for the Planner API service.
 */

package planner

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"maps"
	"net/http"
	"strings"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

const (
	pressureChangeHeartbeatInterval = 30 * time.Second
	createFlavorPattern             = "/api/v1/flavors/{name}"
	getFlavorPressurePattern        = "/api/v1/flavors/{name}/pressure"
	createAuthTokenPattern          = "/api/v1/auth/token/{name}"
	deleteAuthTokenPattern          = "/api/v1/auth/token/{name}"
	healthPattern                   = "/health"
	allFlavorName                   = "_"
	flavorPlatform                  = "github" // Currently only github is supported
)

// FlavorStore is a small interface that matches the relevant method on internal/database.Database.
type FlavorStore interface {
	AddFlavor(ctx context.Context, flavor *database.Flavor) error
	ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error)
	GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error)
	SubscribeToPressureUpdate(ctx context.Context) (<-chan struct{}, error)
}

// AuthStore is an interface that provides authorization token management.
type AuthStore interface {
	CreateAuthToken(ctx context.Context, name string) ([32]byte, error)
	DeleteAuthToken(ctx context.Context, name string) error
}

// Server holds dependencies for the planner HTTP handlers.
type Server struct {
	metrics    *Metrics
	mux        *http.ServeMux
	store      FlavorStore
	auth       AuthStore
	adminToken string
	ticker     <-chan time.Time
}

// NewServer creates a new Server with the given dependencies.
func NewServer(store FlavorStore, auth AuthStore, metrics *Metrics, adminToken string, ticker <-chan time.Time) *Server {
	s := &Server{store: store, auth: auth, adminToken: adminToken, mux: http.NewServeMux(), metrics: metrics, ticker: ticker}

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

	w.Header().Set("Cache-Control", "no-cache")

	query := r.URL.Query()
	flavorName := r.PathValue("name")
	stream := strings.ToLower(query.Get("stream")) == "true"
	var ch <-chan struct{}
	if stream {
		ch, err = s.store.SubscribeToPressureUpdate(r.Context())
		if err != nil {
			http.Error(w, fmt.Sprintf("failed to subscribe to pressure updates: %v", err), http.StatusInternalServerError)
			return
		}
	}

	pressures, err = s.getPressures(r.Context(), flavorPlatform, flavorName)

	if err != nil {
		http.Error(w, fmt.Sprintf("failed to get flavor pressure: %v", err), http.StatusInternalServerError)
		return
	}

	if len(pressures) == 0 {
		http.Error(w, "flavor not found", http.StatusNotFound)
		return
	}

	if !stream {
		respondWithJSON(w, http.StatusOK, pressures)
		return
	}

	// Handle streaming requests
	w.Header().Set("Content-Type", "application/x-ndjson")
	w.Header().Set("Connection", "keep-alive")
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Unable to setup HTTP streaming", http.StatusInternalServerError)
		return
	}

	if err := json.NewEncoder(w).Encode(pressures); err != nil {
		slog.ErrorContext(r.Context(), "failed to encode initial pressures", "error", err)
		http.Error(w, "failed to encode pressures", http.StatusInternalServerError)
		return
	}
	flusher.Flush()

	for {
		select {
		case <-r.Context().Done():
			slog.InfoContext(r.Context(), "client connection terminated")
			return
		// Sending pressure as periodic heartbeats to keep the connection alive
		case <-s.ticker:
			newPressures, err := s.getPressures(r.Context(), flavorPlatform, flavorName)
			if err != nil {
				slog.ErrorContext(r.Context(), "failed to get flavor pressure for streaming", "error", err)
				return
			}
			if err := json.NewEncoder(w).Encode(newPressures); err != nil {
				slog.ErrorContext(r.Context(), "failed to encode pressure update", "error", err)
				return
			}
			flusher.Flush()
			pressures = newPressures
		case _, ok := <-ch:
			if !ok {
				slog.InfoContext(r.Context(), "pressure update channel closed")
				return
			}

			newPressures, err := s.getPressures(r.Context(), flavorPlatform, flavorName)
			if err != nil {
				slog.ErrorContext(r.Context(), "failed to get flavor pressure for streaming", "error", err)
				return
			}
			if !maps.Equal(pressures, newPressures) {
				if err := json.NewEncoder(w).Encode(newPressures); err != nil {
					slog.ErrorContext(r.Context(), "failed to encode pressure update", "error", err)
					return
				}
				flusher.Flush()
			}
			pressures = newPressures
		}
	}
}

func (s *Server) getPressures(ctx context.Context, platform string, flavorName string) (map[string]int, error) {
	switch flavorName {
	case allFlavorName:
		return s.store.GetPressures(ctx, flavorPlatform)
	default:
		return s.store.GetPressures(ctx, flavorPlatform, flavorName)
	}
}

// health handles health check requests.
func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	respondWithJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) adminProtected(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authorization_header := r.Header.Get("Authorization")
		parts := strings.SplitN(authorization_header, " ", 2)
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
	name := r.PathValue("name")
	if name == "" {
		http.Error(w, "missing token name", http.StatusBadRequest)
		return
	}
	token, err := s.auth.CreateAuthToken(r.Context(), name)
	if err == nil {
		respondWithJSON(w, http.StatusCreated, tokenResponse{Name: name, Token: base64.RawURLEncoding.EncodeToString(token[:])})
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
	name := r.PathValue("name")
	if name == "" {
		http.Error(w, "missing token name", http.StatusBadRequest)
		return
	}
	if err := s.auth.DeleteAuthToken(r.Context(), name); err != nil {
		if errors.Is(err, database.ErrNotExist) {
			w.WriteHeader(http.StatusNoContent)
			return
		}
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
