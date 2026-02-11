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
	flavorPattern            = "/api/v1/flavors/{name}"
	getFlavorPressurePattern = "/api/v1/flavors/{name}/pressure"
	authTokenBasePattern     = "/api/v1/auth/token"
	createAuthTokenPattern   = "/api/v1/auth/token/{name}"
	deleteAuthTokenPattern   = "/api/v1/auth/token/{name}"
	jobPattern               = "/api/v1/jobs/{platform}/{id}"
	jobsPattern              = "/api/v1/jobs/{platform}"
	healthPattern            = "/health"
	allFlavorName            = "_"
	flavorPlatform           = "github" // Currently only github is supported
)

var (
	// errFieldAlreadySet is returned when attempting to update a field that is already set.
	errFieldAlreadySet = errors.New("field is already set")
)

// FlavorStore is a small interface that matches the relevant method on internal/database.Database.
type FlavorStore interface {
	AddFlavor(ctx context.Context, flavor *database.Flavor) error
	ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error)
	EnableFlavor(ctx context.Context, platform, name string) error
	DisableFlavor(ctx context.Context, platform, name string) error
	GetFlavor(ctx context.Context, name string) (*database.Flavor, error)
	DeleteFlavor(ctx context.Context, platform string, name string) error
	GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error)
	SubscribeToPressureUpdate(ctx context.Context) (<-chan struct{}, error)
	ListJobs(ctx context.Context, platform string, option ...database.ListJobOptions) ([]database.Job, error)
	UpdateJobStarted(ctx context.Context, platform, id string, startedAt time.Time, raw map[string]interface{}) error
	UpdateJobCompleted(ctx context.Context, platform, id string, completedAt time.Time, raw map[string]interface{}) error
}

// AuthStore is an interface that provides authorization token management.
type AuthStore interface {
	CreateAuthToken(ctx context.Context, name string) ([32]byte, error)
	ListAuthTokens(ctx context.Context) ([]string, error)
	DeleteAuthToken(ctx context.Context, name string) error
	VerifyAuthToken(ctx context.Context, token [32]byte) (string, error)
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
	// General endpoints require either a valid general token or the admin token
	s.mux.Handle("POST "+flavorPattern, otelhttp.WithRouteTag(flavorPattern, s.tokenProtected(http.HandlerFunc(s.createFlavor))))
	s.mux.Handle("GET "+flavorPattern, otelhttp.WithRouteTag(flavorPattern, s.tokenProtected(http.HandlerFunc(s.getFlavor))))
	s.mux.Handle("PATCH "+flavorPattern, otelhttp.WithRouteTag(flavorPattern, s.tokenProtected(http.HandlerFunc(s.updateFlavor))))
	s.mux.Handle("DELETE "+flavorPattern, otelhttp.WithRouteTag(flavorPattern, s.tokenProtected(http.HandlerFunc(s.deleteFlavor))))
	s.mux.Handle("GET "+getFlavorPressurePattern, otelhttp.WithRouteTag(getFlavorPressurePattern, s.tokenProtected(http.HandlerFunc(s.getFlavorPressure))))
	s.mux.Handle("POST "+createAuthTokenPattern, otelhttp.WithRouteTag(createAuthTokenPattern, s.adminProtected(http.HandlerFunc(s.createAuthToken))))
	s.mux.Handle("GET "+authTokenBasePattern, otelhttp.WithRouteTag(authTokenBasePattern, s.adminProtected(http.HandlerFunc(s.listAuthTokens))))
	s.mux.Handle("DELETE "+deleteAuthTokenPattern, otelhttp.WithRouteTag(deleteAuthTokenPattern, s.adminProtected(http.HandlerFunc(s.deleteAuthToken))))
	s.mux.Handle("GET "+jobsPattern, otelhttp.WithRouteTag(jobsPattern, s.tokenProtected(http.HandlerFunc(s.listJobs))))
	s.mux.Handle("GET "+jobPattern, otelhttp.WithRouteTag(jobPattern, s.tokenProtected(http.HandlerFunc(s.getJob))))
	s.mux.Handle("PATCH "+jobPattern, otelhttp.WithRouteTag(jobPattern, s.tokenProtected(http.HandlerFunc(s.updateJob))))
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
	req, err := decodeFlavorInRequestBody(r)
	if err != nil {
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

	err = s.store.AddFlavor(r.Context(), flavor)
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

// getFlavor handles retrieving a flavor or listing all flavors.
// If the flavor name is allFlavorName, returns all flavors with status code 200.
// If the flavor is not found, returns status code 404.
// If getting the flavor fails, returns status code 500.
// If successful, returns status code 200 with the flavor JSON.
func (s *Server) getFlavor(w http.ResponseWriter, r *http.Request) {
	flavorName := r.PathValue("name")
	if flavorName == allFlavorName {
		// List all flavors
		flavors, err := s.store.ListFlavors(r.Context(), "")
		if err != nil {
			http.Error(w, fmt.Sprintf("cannot list flavors: %v", err), http.StatusInternalServerError)
			return
		}
		flavorNames := make([]string, 0, len(flavors))
		for _, flavor := range flavors {
			flavorNames = append(flavorNames, flavor.Name)
		}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(map[string][]string{"names": flavorNames}); err != nil {
			http.Error(w, fmt.Sprintf("cannot encode flavors: %v", err), http.StatusInternalServerError)
		}
		return
	}
	flavor, err := s.store.GetFlavor(r.Context(), flavorName)
	if errors.Is(err, database.ErrNotExist) {
		http.Error(w, "cannot get flavor", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot get flavor %v: %v", flavorName, err), http.StatusInternalServerError)
		return
	}

	respondWithJSON(w, http.StatusOK, flavor)
}

type updateFlavorRequest struct {
	IsDisabled *bool `json:"is_disabled"`
}

// updateFlavor handles updating an existing flavor's disabled status.
func (s *Server) updateFlavor(w http.ResponseWriter, r *http.Request) {
	decoder := json.NewDecoder(r.Body)
	defer r.Body.Close()

	req := &updateFlavorRequest{}
	if err := decoder.Decode(req); err != nil {
		http.Error(w, fmt.Sprintf("invalid payload: %v", err), http.StatusBadRequest)
		return
	}

	if req.IsDisabled == nil {
		http.Error(w, "is_disabled field is required", http.StatusBadRequest)
		return
	}

	flavorName := r.PathValue("name")
	if flavorName == allFlavorName {
		http.Error(w, "update all flavors is not supported", http.StatusBadRequest)
		return
	}

	var err error
	if *req.IsDisabled {
		err = s.store.DisableFlavor(r.Context(), flavorPlatform, flavorName)
	} else {
		err = s.store.EnableFlavor(r.Context(), flavorPlatform, flavorName)
	}

	if errors.Is(err, database.ErrNotExist) {
		http.Error(w, "cannot find flavor to update", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot update flavor: %v", err), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// deleteFlavor handles deleting an existing flavor.
// If the flavor name is allFlavorName, returns status code 400.
// If deleting the flavor fails, returns status code 500.
// If successful, returns status code 200.
func (s *Server) deleteFlavor(w http.ResponseWriter, r *http.Request) {
	flavorName := r.PathValue("name")
	if flavorName == allFlavorName {
		http.Error(w, "delete all flavors is not supported", http.StatusBadRequest)
		return
	}
	err := s.store.DeleteFlavor(r.Context(), flavorPlatform, flavorName)
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot delete flavor: %v", err), http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}

// getFlavorPressure handles retrieving the pressure for a specific or all flavors.
func (s *Server) getFlavorPressure(w http.ResponseWriter, r *http.Request) {
	var pressures = map[string]int{}
	var err error

	w.Header().Set("Cache-Control", "no-cache")

	query := r.URL.Query()
	flavorName := r.PathValue("name")
	stream := strings.ToLower(query.Get("stream")) == "true"
	var pressureChange <-chan struct{}
	if stream {
		pressureChange, err = s.store.SubscribeToPressureUpdate(r.Context())
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

	flushJSONToStream(w, flusher, pressures)
	s.streamFlavorPressureUpdates(w, r, flavorName, flusher, pressures, pressureChange)
}

func (s *Server) streamFlavorPressureUpdates(w http.ResponseWriter, r *http.Request, flavorName string, flusher http.Flusher, pressures map[string]int, pressureChange <-chan struct{}) {
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
			flushJSONToStream(w, flusher, newPressures)
			pressures = newPressures
		case _, ok := <-pressureChange:
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
				flushJSONToStream(w, flusher, newPressures)
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

// respondUnauthorized sends a 401 response with proper WWW-Authenticate header.
func respondUnauthorized(w http.ResponseWriter) {
	w.Header().Set("WWW-Authenticate", "Bearer")
	http.Error(w, "unauthorized", http.StatusUnauthorized)
}

func (s *Server) adminProtected(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authorizationHeader := r.Header.Get("Authorization")
		parts := strings.SplitN(authorizationHeader, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
			http.Error(w, "invalid authorization header", http.StatusBadRequest)
			return
		}
		if parts[1] != s.adminToken {
			respondUnauthorized(w)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// tokenProtected allows either the admin token or a valid general token from the DB.
func (s *Server) tokenProtected(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authorizationHeader := r.Header.Get("Authorization")
		parts := strings.SplitN(authorizationHeader, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
			http.Error(w, "invalid authorization header", http.StatusBadRequest)
			return
		}
		tokenStr := parts[1]
		if tokenStr == s.adminToken {
			next.ServeHTTP(w, r)
			return
		}
		raw, err := base64.RawURLEncoding.DecodeString(tokenStr)
		if err != nil || len(raw) != 32 {
			respondUnauthorized(w)
			return
		}
		var tok [32]byte
		copy(tok[:], raw)
		if _, err := s.auth.VerifyAuthToken(r.Context(), tok); err != nil {
			respondUnauthorized(w)
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

// listAuthTokens handles listing of all general authentication tokens (admin-protected).
// On database failures, returns status code 500.
// Returns a JSON array of token names.
func (s *Server) listAuthTokens(w http.ResponseWriter, r *http.Request) {
	names, err := s.auth.ListAuthTokens(r.Context())
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot list tokens: %v", err), http.StatusInternalServerError)
		return
	}
	respondWithJSON(w, http.StatusOK, map[string]any{"names": names})
}

// deleteAuthToken handles deletion of a general authentication token (admin-protected).
func (s *Server) deleteAuthToken(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("name")
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

// listJobs handles retrieving jobs by platform.
func (s *Server) listJobs(w http.ResponseWriter, r *http.Request) {
	platform := r.PathValue("platform")

	jobs, err := s.store.ListJobs(r.Context(), platform, database.ListJobOptions{})
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot list jobs: %v", err), http.StatusInternalServerError)
		return
	}

	respondWithJSON(w, http.StatusOK, jobs)
}

// getJob handles retrieving a single job by platform and ID.
func (s *Server) getJob(w http.ResponseWriter, r *http.Request) {
	platform := r.PathValue("platform")
	id := r.PathValue("id")

	jobs, err := s.store.ListJobs(r.Context(), platform, database.ListJobOptions{WithId: id})
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot get job: %v", err), http.StatusInternalServerError)
		return
	}
	if len(jobs) == 0 {
		http.Error(w, "job not found", http.StatusNotFound)
		return
	}

	respondWithJSON(w, http.StatusOK, jobs[0])
}

type updateJobRequest struct {
	StartedAt   *time.Time `json:"started_at,omitempty"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
}

// updateJob handles updating a job's started_at and/or completed_at fields that are not yet set.
// Non-atomic operation: concurrent updates may race, but is acceptable for debug use.
func (s *Server) updateJob(w http.ResponseWriter, r *http.Request) {
	platform := r.PathValue("platform")
	id := r.PathValue("id")

	job, err := s.store.ListJobs(r.Context(), platform, database.ListJobOptions{WithId: id})
	if err != nil {
		http.Error(w, fmt.Sprintf("cannot get job: %v", err), http.StatusInternalServerError)
		return
	}
	if len(job) == 0 {
		http.Error(w, "job not found", http.StatusNotFound)
		return
	}

	decoder := json.NewDecoder(r.Body)
	defer r.Body.Close()

	req := updateJobRequest{}
	if err := decoder.Decode(&req); err != nil {
		http.Error(w, fmt.Sprintf("invalid payload: %v", err), http.StatusBadRequest)
		return
	}

	if err := s.applyJobUpdates(r.Context(), req, job[0], platform, id); err != nil {
		if errors.Is(err, errFieldAlreadySet) {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		http.Error(w, fmt.Sprintf("cannot update job: %v", err), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// applyJobUpdates applies the updates from the request to the job.
func (s *Server) applyJobUpdates(ctx context.Context, req updateJobRequest, job database.Job, platform, id string) error {
	if req.StartedAt != nil {
		if job.StartedAt != nil {
			return fmt.Errorf("%w: cannot update started_at", errFieldAlreadySet)
		}
		if err := s.store.UpdateJobStarted(ctx, platform, id, *req.StartedAt, nil); err != nil {
			return fmt.Errorf("cannot update job started_at: %w", err)
		}
	}

	if req.CompletedAt != nil {
		if job.CompletedAt != nil {
			return fmt.Errorf("%w: cannot update completed_at", errFieldAlreadySet)
		}
		if err := s.store.UpdateJobCompleted(ctx, platform, id, *req.CompletedAt, nil); err != nil {
			return fmt.Errorf("cannot update job completed_at: %w", err)
		}
	}

	return nil
}

// respondWithJSON sends a JSON response with the given status code and payload.
func respondWithJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(payload)
}

// flushJSONToStream encodes and flushes JSON data to the response writer.
func flushJSONToStream(w http.ResponseWriter, flusher http.Flusher, payload any) error {
	err := json.NewEncoder(w).Encode(payload)
	if err != nil {
		return err
	}
	flusher.Flush()
	return nil
}

func decodeFlavorInRequestBody(r *http.Request) (*flavorRequest, error) {
	decoder := json.NewDecoder(r.Body)
	defer r.Body.Close()

	req := &flavorRequest{}
	if err := decoder.Decode(req); err != nil {
		return nil, fmt.Errorf("invalid payload: %w", err)
	}
	return req, nil
}
