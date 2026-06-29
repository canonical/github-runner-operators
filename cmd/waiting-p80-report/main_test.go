// Copyright 2026 Canonical Ltd.
// See LICENSE file for licensing details.

package main

import (
	"bytes"
	"strings"
	"testing"
	"time"
)

func TestBuildQuery(t *testing.T) {
	q := buildQuery()
	checks := []struct{ name, want string }{
		{"percentile_cont(0.8)", "percentile_cont(0.8)"},
		{"started_at guard", "started_at IS NOT NULL"},
		{"created_at guard", "created_at IS NOT NULL"},
		{"only jobs we own", "assigned_flavor IS NOT NULL"},
		{"negative wait clamped to zero", "GREATEST(EXTRACT(EPOCH FROM (started_at - created_at)), 0)"},
		{"day bucket", "date_trunc('day', started_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"},
		{"group by day", "GROUP BY day, platform"},
		{"from param", "@from"},
		{"to param", "@to"},
	}
	for _, c := range checks {
		if !strings.Contains(q, c.want) {
			t.Fatalf("%s: query missing %q\nquery:\n%s", c.name, c.want, q)
		}
	}
	// Negative waits are clamped to 0, not filtered out, so the row-dropping
	// guard must be gone — otherwise fast jobs would be excluded and P80 skewed up.
	if strings.Contains(q, "started_at >= created_at") {
		t.Fatalf("query must not exclude negative waits; clamp to 0 instead\nquery:\n%s", q)
	}
}

func TestWriteCSV(t *testing.T) {
	rows := []dailyP80Row{
		{Day: time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC), Platform: "github", P80Seconds: 210.5, SampleCount: 42},
		{Day: time.Date(2026, 5, 2, 0, 0, 0, 0, time.UTC), Platform: "github", P80Seconds: 0, SampleCount: 0},
	}
	var buf bytes.Buffer
	if err := writeCSV(&buf, rows, false); err != nil {
		t.Fatal(err)
	}
	got := buf.String()
	want := "day,platform,p80_seconds,sample_count\n2026-05-01,github,210.5,42\n2026-05-02,github,0,0\n"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestWriteCSV_NoHeader(t *testing.T) {
	rows := []dailyP80Row{
		{Day: time.Date(2026, 5, 1, 0, 0, 0, 0, time.UTC), Platform: "github", P80Seconds: 210.5, SampleCount: 42},
	}
	var buf bytes.Buffer
	if err := writeCSV(&buf, rows, true); err != nil {
		t.Fatal(err)
	}
	got := buf.String()
	want := "2026-05-01,github,210.5,42\n"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestWriteCSV_Empty(t *testing.T) {
	var buf bytes.Buffer
	if err := writeCSV(&buf, nil, false); err != nil {
		t.Fatal(err)
	}
	want := "day,platform,p80_seconds,sample_count\n"
	if got := buf.String(); got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}
