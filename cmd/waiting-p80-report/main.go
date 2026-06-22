// Package main is a standalone CLI that extracts the daily P80 of GitHub runner
// job waiting time from the planner's PostgreSQL database into a CSV.
//
// It is not part of the planner charm. Run it ad hoc, from cron, or in CI. It
// reads the planner's `job` table read-only.
//
// Usage:
//
//	waiting-p80-report -dsn "$POSTGRESQL_DB_CONNECT_STRING" \
//	    -from 2026-05-01 -to 2026-05-31 -o p80.csv
package main

import (
	"context"
	"encoding/csv"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type config struct {
	dsn     string
	from    time.Time
	to      time.Time
	out     string
	verbose bool
}

func parseConfig() (config, error) {
	cfg := config{}
	flag.StringVar(&cfg.dsn, "dsn", "", "PostgreSQL connection string (or set POSTGRESQL_DB_CONNECT_STRING)")
	flag.StringVar(&cfg.out, "o", "", "output CSV path (default: stdout)")
	fromStr := flag.String("from", "", "start date YYYY-MM-DD (inclusive, UTC)")
	toStr := flag.String("to", "", "end date YYYY-MM-DD (inclusive, UTC); defaults to today UTC")
	flag.BoolVar(&cfg.verbose, "v", false, "verbose logging to stderr")
	flag.Parse()

	if cfg.dsn == "" {
		cfg.dsn = os.Getenv("POSTGRESQL_DB_CONNECT_STRING")
	}
	if cfg.dsn == "" {
		return cfg, fmt.Errorf("missing -dsn or POSTGRESQL_DB_CONNECT_STRING")
	}

	if *fromStr == "" {
		return cfg, fmt.Errorf("missing -from (YYYY-MM-DD)")
	}
	var err error
	cfg.from, err = time.Parse("2006-01-02", *fromStr)
	if err != nil {
		return cfg, fmt.Errorf("invalid -from: %w", err)
	}
	if *toStr == "" {
		cfg.to = time.Now().UTC().Truncate(24 * time.Hour)
	} else {
		cfg.to, err = time.Parse("2006-01-02", *toStr)
		if err != nil {
			return cfg, fmt.Errorf("invalid -to: %w", err)
		}
	}
	// -to is inclusive; bump to end of the day for SQL half-open range.
	cfg.to = cfg.to.Add(24 * time.Hour)
	if !cfg.to.After(cfg.from) {
		return cfg, fmt.Errorf("-to must be after -from")
	}
	return cfg, nil
}

func main() {
	cfg, err := parseConfig()
	if err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		flag.Usage()
		os.Exit(2)
	}
	if err := run(cfg); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func run(cfg config) error {
	ctx := context.Background()
	rows, err := queryRows(ctx, cfg)
	if err != nil {
		return err
	}
	if cfg.verbose {
		fmt.Fprintf(os.Stderr, "retrieved %d rows\n", len(rows))
	}
	var w io.Writer = os.Stdout
	if cfg.out != "" {
		f, err := os.Create(cfg.out)
		if err != nil {
			return fmt.Errorf("open output: %w", err)
		}
		defer f.Close()
		w = f
	}
	return writeCSV(w, rows)
}

// dailyP80Row is one row of the daily P80 rollup.
type dailyP80Row struct {
	Day         time.Time
	Platform    string
	P80Seconds  float64
	SampleCount int
}

func buildQuery() string {
	return `
		SELECT date_trunc('day', started_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS day,
		       platform,
		       percentile_cont(0.8) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (started_at - created_at))) AS p80_seconds,
		       COUNT(*) AS sample_count
		FROM job
		WHERE started_at IS NOT NULL
		  AND created_at IS NOT NULL
		  AND started_at >= created_at
		  AND started_at >= @from
		  AND started_at < @to
		GROUP BY day, platform
		ORDER BY day, platform`
}

func queryRows(ctx context.Context, cfg config) ([]dailyP80Row, error) {
	pool, err := pgxpool.New(ctx, cfg.dsn)
	if err != nil {
		return nil, fmt.Errorf("connect: %w", err)
	}
	defer pool.Close()

	rows, err := pool.Query(ctx, buildQuery(), pgx.NamedArgs{
		"from": cfg.from.UTC(),
		"to":   cfg.to.UTC(),
	})
	if err != nil {
		return nil, fmt.Errorf("query: %w", err)
	}
	defer rows.Close()

	var out []dailyP80Row
	for rows.Next() {
		var r dailyP80Row
		if err := rows.Scan(&r.Day, &r.Platform, &r.P80Seconds, &r.SampleCount); err != nil {
			return nil, fmt.Errorf("scan: %w", err)
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// writeCSV writes the daily P80 rows as CSV with a header line. Days with no jobs
// do not appear in rows (the SQL GROUP BY omits them), so absent days are simply
// absent from the CSV. Flush errors (e.g. disk full, broken pipe) are surfaced
// via csv.Writer.Error rather than silently dropped.
func writeCSV(w io.Writer, rows []dailyP80Row) error {
	cw := csv.NewWriter(w)
	if err := cw.Write([]string{"day", "platform", "p80_seconds", "sample_count"}); err != nil {
		return err
	}
	for _, r := range rows {
		if err := cw.Write([]string{
			r.Day.UTC().Format("2006-01-02"),
			r.Platform,
			strconv.FormatFloat(r.P80Seconds, 'f', -1, 64),
			strconv.Itoa(r.SampleCount),
		}); err != nil {
			return err
		}
	}
	cw.Flush()
	return cw.Error()
}
