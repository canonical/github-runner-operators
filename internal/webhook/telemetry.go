package webhook

import (
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
	pkg            = "github.com/canonical/mayfly/internal/webhook"
	meter          = otel.Meter(pkg)
	trace          = otel.Tracer(pkg)
	inboundWebhook = must(
		meter.Int64Counter(
			"mayfly.webhook.gateway.inbound",
			metric.WithDescription("webhooks received by the webhook gateway"),
			metric.WithUnit("{webhook}"),
		),
	)
	inboundWebhookErrors = must(
		meter.Int64Counter(
			"mayfly.webhook.gateway.inbound.errors",
			metric.WithDescription("webhooks receiving failed in the webhook gateway"),
			metric.WithUnit("{error}"),
		),
	)
	outboundWebhook = must(
		meter.Int64Counter(
			"mayfly.webhook.gateway.outbound",
			metric.WithDescription("webhooks transmitted by the webhook gateway"),
			metric.WithUnit("{webhook}"),
		),
	)
	outboundWebhookErrors = must(
		meter.Int64Counter(
			"mayfly.webhook.gateway.outbound.errors",
			metric.WithDescription("webhooks transmitting failed in the webhook gateway"),
			metric.WithUnit("{error}"),
		),
	)
)
