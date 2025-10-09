package telemetry

import (
	"context"
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
)

func TestInMemoryMetrics(t *testing.T) {
	ctx := context.Background()
	meter := otel.Meter("github.com/canonical/mayfly/internal/telemetry")
	testMetric, err := meter.Int64Gauge("test.metric")
	assert.NoError(t, err)

	defer assert.NoError(t, Shutdown(ctx))
	assert.NoError(t, os.Setenv("OTEL_METRICS_EXPORTER", "memory"))
	assert.NoError(t, Start(ctx), "failed to start telemetry")
	assert.NotNil(t, ManualReader, "in-memory metrics provider should be initialized")

	testMetric.Record(ctx, 1)
	var rm metricdata.ResourceMetrics
	assert.NoError(t, ManualReader.Collect(ctx, &rm), "failed to collect metrics")
	names := make([]string, 0)
	for _, sm := range rm.ScopeMetrics {
		for _, m := range sm.Metrics {
			names = append(names, m.Name)
		}
	}
	assert.Contains(t, names, "test.metric", "metric names should contain test")
}
