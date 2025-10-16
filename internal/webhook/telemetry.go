package webhook

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
	pkg            = "github.com/canonical/github-runner-operators/internal/webhook"
	meter          = otel.Meter(pkg)
	trace          = otel.Tracer(pkg)
	logger         = telemetry.NewLogger("github.com/canonical/github-runner-operators/internal/webhook")
	inboundWebhook = must(
		meter.Int64Counter(
			"github-runner.webhook.gateway.inbound",
			metric.WithDescription("webhooks received by the webhook gateway"),
			metric.WithUnit("{webhook}"),
		),
	)
	inboundWebhookErrors = must(
		meter.Int64Counter(
			"github-runner.webhook.gateway.inbound.errors",
			metric.WithDescription("webhooks receiving failures in the webhook gateway"),
			metric.WithUnit("{error}"),
		),
	)
	outboundWebhook = must(
		meter.Int64Counter(
			"github-runner.webhook.gateway.outbound",
			metric.WithDescription("webhooks transmitted by the webhook gateway"),
			metric.WithUnit("{webhook}"),
		),
	)
	outboundWebhookErrors = must(
		meter.Int64Counter(
			"github-runner.webhook.gateway.outbound.errors",
			metric.WithDescription("webhooks transmitting failures in the webhook gateway"),
			metric.WithUnit("{error}"),
		),
	)
)
