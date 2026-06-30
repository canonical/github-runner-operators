/*
 * Copyright 2026 Canonical Ltd.
 * See LICENSE file for licensing details.
 */

package redelivery

import (
	"github.com/canonical/github-runner-operators/internal/telemetry"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/metric"
)

func must[T any](obj T, err error) T {
	if err != nil {
		panic(err)
	}
	return obj
}

var (
	pkg    = "github.com/canonical/github-runner-operators/internal/redelivery"
	meter  = otel.Meter(pkg)
	tracer = otel.Tracer(pkg)
	logger = telemetry.NewLogger(pkg)

	redeliveryCount = must(
		meter.Int64Counter(
			"github-runner.webhook.redelivery.count",
			metric.WithDescription("number of webhooks successfully redelivered"),
			metric.WithUnit("{webhook}"),
		),
	)
	redeliveryErrors = must(
		meter.Int64Counter(
			"github-runner.webhook.redelivery.errors",
			metric.WithDescription("number of webhook redelivery failures"),
			metric.WithUnit("{error}"),
		),
	)
)
