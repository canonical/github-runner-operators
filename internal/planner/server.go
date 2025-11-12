/*
 * Copyright 2025 Canonical Ltd.
 * See LICENSE file for licensing details.
 *
 * Package planner provides HTTP handlers for the Planner API service.
 */

package planner

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"

	"github.com/canonical/github-runner-operators/internal/database"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
)

type contextKey string

const tokenNameKey contextKey = "tokenName"
const createFlavorPattern = "/api/v1/flavors/{name}"

// FlavorStore is a small interface that matches the relevant method on internal/database.Database.
type FlavorStore interface {
	AddFlavor(ctx context.Context, flavor *database.Flavor) error
	ListFlavors(ctx context.Context, platform string) ([]database.Flavor, error)
	GetPressures(ctx context.Context, platform string, flavors ...string) (map[string]int, error)
	VerifyAuthToken(ctx context.Context, token [32]byte) (string, error)
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
	s.mux.Handle("POST "+createFlavorPattern, otelhttp.WithRouteTag(createFlavorPattern, s.AuthMiddleware(http.HandlerFunc(s.createFlavor))))

	return s
}

// ServeHTTP routes incoming HTTP requests to the appropriate handler methods.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mux.ServeHTTP(w, r)
}

// AuthMiddleware is an HTTP middleware that checks for a valid user token
// in the Authorization header.
func (s *Server) AuthMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Expect header contains Authorization: Bearer <token>
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}

		tokenStr := strings.TrimPrefix(authHeader, "Bearer ")
		tokenBytes, err := hex.DecodeString(tokenStr)
		if err != nil || len(tokenBytes) != 32 {
			http.Error(w, "invalid token format", http.StatusUnauthorized)
			return
		}

		var tokenArr [32]byte
		copy(tokenArr[:], tokenBytes)
		name, err := s.store.VerifyAuthToken(r.Context(), tokenArr)
		if err != nil {
			if errors.Is(err, database.ErrNotExist) {
				http.Error(w, "unauthorized", http.StatusUnauthorized)
				return
			}
			http.Error(w, fmt.Sprintf("token verification failed: %v", err), http.StatusInternalServerError)
			return
		}

		// Store token name to request context for downstream handlers
		ctx := context.WithValue(r.Context(), tokenNameKey, name)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
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
	if err == nil || errors.Is(err, database.ErrExist) {
		s.updateMetrics(r.Context(), flavor)
		w.WriteHeader(http.StatusCreated)
		return
	}

	http.Error(w, fmt.Sprintf("failed to create flavor: %v", err), http.StatusInternalServerError)
}

func (s *Server) updateMetrics(ctx context.Context, flavor *database.Flavor) {
	pressure, err := s.store.GetPressures(ctx, flavor.Platform, flavor.Name)
	if err != nil {
		log.Printf("Failed to fetch pressure for flavor %s: %v", flavor.Name, err)
		return
	}
	pressureValue, ok := pressure[flavor.Name]
	if !ok {
		pressureValue = 0
	}
	s.metrics.ObserveFlavorPressure(flavor.Platform, flavor.Name, int64(pressureValue))
}
