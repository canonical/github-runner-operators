package planner

import (
	"context"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/canonical/github-runner-operators/internal/database"
)

// TestCreateFlavorIntegration exercises the full HTTP path against a real Postgres database.
// It requires TEST_DATABASE_URI to be set (postgres://...); otherwise it will be skipped.
func TestCreateFlavorIntegration(t *testing.T) {
	uri := os.Getenv("TEST_DATABASE_URI")
	if uri == "" {
		t.Skip("TEST_DATABASE_URI not set; skipping integration test")
	}

	ctx := context.Background()

	// Apply migrations and connect
	if err := database.Migrate(ctx, uri); err != nil {
		t.Fatalf("migrate failed: %v", err)
	}
	db, err := database.New(ctx, uri)
	if err != nil {
		t.Fatalf("db connect failed: %v", err)
	}

	// Create an auth token to authenticate requests
	tokenName := "it-planner-" + time.Now().Format("20060102-150405.000000000")
	token, err := db.CreateAuthToken(ctx, tokenName)
	if err != nil {
		t.Fatalf("create auth token failed: %v", err)
	}
	tokenHex := hex.EncodeToString(token[:])

	// Ensure clean state for the flavor we will create
	const platform = "github"
	const flavorName = "it-flavor"
	_ = db.DeleteFlavor(ctx, platform, flavorName)

	metrics := NewMetrics()
	srv := NewServer(db, metrics)
	ts := httptest.NewServer(srv)
	defer ts.Close()

	// Prepare payload
	body := map[string]any{
		"platform": platform,
		"labels":   []string{"self-hosted", "amd64"},
		"priority": 42,
	}
	b, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	// Send request
	req, err := http.NewRequest(http.MethodPost, ts.URL+"/api/v1/flavors/"+flavorName, bytesReader(b))
	if err != nil {
		t.Fatalf("new request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+tokenHex)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		t.Fatalf("unexpected status: %d", resp.StatusCode)
	}

	// Verify flavor exists in DB with expected fields
	flavors, err := db.ListFlavors(ctx, platform)
	if err != nil {
		t.Fatalf("list flavors: %v", err)
	}
	found := false
	for _, f := range flavors {
		if f.Name == flavorName {
			found = true
			if f.Priority != 42 {
				t.Fatalf("unexpected priority: %d", f.Priority)
			}
			// labels are stored as []string; order should be preserved as sent
			if len(f.Labels) != 2 || f.Labels[0] != "self-hosted" || f.Labels[1] != "amd64" {
				t.Fatalf("unexpected labels: %#v", f.Labels)
			}
			break
		}
	}
	if !found {
		t.Fatalf("flavor %q not found in db", flavorName)
	}

	// Cleanup
	_ = db.DeleteFlavor(ctx, platform, flavorName)
	_ = db.DeleteAuthToken(ctx, tokenName)
}

// bytesReader returns an io.Reader for the given byte slice without bringing in extra deps inline.
func bytesReader(b []byte) *bytesReaderT { return &bytesReaderT{b: b} }

type bytesReaderT struct{ b []byte }

func (r *bytesReaderT) Read(p []byte) (int, error) {
	if len(r.b) == 0 {
		return 0, io.EOF
	}
	n := copy(p, r.b)
	r.b = r.b[n:]
	return n, nil
}
