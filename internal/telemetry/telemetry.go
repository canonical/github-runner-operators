// Package telemetry initializes OpenTelemetry tracing, metrics, and logging
// based on the standard OTEL_* environment variables. See:
// https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/
//
// # Traces
//
// Enable tracing by setting OTEL_TRACES_EXPORTER=otlp. Typical OTLP settings:
//
//	OTEL_TRACES_EXPORTER=otlp                                 // select the tracing exporter
//	OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317
//	OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=grpc                   // "grpc", "http/protobuf", etc.
//
// # Metrics
//
// Enable metrics by setting OTEL_METRICS_EXPORTER to one of: prometheus, memory, or otlp.
// If OTEL_METRICS_EXPORTER is not set, the in-memory exporter ("memory") is used.
//
// Prometheus metrics (pull) example:
//
//	OTEL_METRICS_EXPORTER=prometheus
//	OTEL_EXPORTER_PROMETHEUS_HOST=localhost     // prometheus listen host, default: localhost
//	OTEL_EXPORTER_PROMETHEUS_PORT=9464          // prometheus listen port, default: 9464
//
// OTLP metrics (push) example:
//
//	OTEL_METRICS_EXPORTER=otlp
//	OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://127.0.0.1:9009/otlp/v1/metrics
//	OTEL_EXPORTER_OTLP_METRICS_PROTOCOL=http/protobuf    // "grpc", "http/protobuf", etc.
//
// # Logs
//
// Enable OpenTelemetry logging by setting OTEL_LOGS_EXPORTER to one of: otlp or console.
// If OpenTelemetry logging is disabled (e.g., OTEL_LOGS_EXPORTER is unset or "none"),
// the package falls back to standard slog output.
//
// OpenTelemetry console logging example:
//
//	OTEL_LOGS_EXPORTER=console
//
// OTLP logging (push) example:
//
//	OTEL_LOGS_EXPORTER=otlp
//	OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:3100/otlp/v1/logs
//	OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/protobuf       // "grpc" or "http/protobuf"

package telemetry

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"testing"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploghttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/exporters/prometheus"
	"go.opentelemetry.io/otel/exporters/stdout/stdoutlog"
	"go.opentelemetry.io/otel/log"
	logglobal "go.opentelemetry.io/otel/log/global"
	"go.opentelemetry.io/otel/log/noop"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/propagation"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	"go.opentelemetry.io/otel/sdk/metric/metricdata"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.37.0"
	"go.opentelemetry.io/otel/trace"
	tracenoop "go.opentelemetry.io/otel/trace/noop"
)

var mu sync.Mutex
var started = false
var shutdown func(context.Context) error
var logger = slog.Default()

// ManualReader is initialized only when the in-memory metric provider is used.
// It will be nil otherwise. ManualReader is primarily intended for use in tests.
var ManualReader *sdkmetric.ManualReader

func envOrDefault(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

// pickProtocol returns the OTLP protocol for the given signal.
// By default, grpc is used. If "http" is specified, it is interpreted as http/protobuf.
func pickProtocol(signal string) string {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_" + signal + "_PROTOCOL")))
	if v == "" {
		v = strings.ToLower(strings.TrimSpace(os.Getenv("OTEL_EXPORTER_OTLP_PROTOCOL")))
	}
	if v == "" {
		return "grpc"
	}
	if v == "http" {
		return "http/protobuf"
	}
	return v
}

func useOtelSlog() bool {
	kind := strings.ToLower(strings.TrimSpace(envOrDefault("OTEL_LOGS_EXPORTER", "none")))
	protocol := pickProtocol("LOGS")
	if kind == "none" || kind == "" {
		return false
	} else if kind == "console" {
		return true
	} else if kind == "otlp" && protocol == "grpc" {
		return true
	} else if kind == "otlp" && strings.HasPrefix(protocol, "http") {
		return true
	} else {
		return false
	}
}

func newLoggerProvider(ctx context.Context, res *resource.Resource) (log.LoggerProvider, func(ctx context.Context) error, error) {
	kind := strings.ToLower(strings.TrimSpace(envOrDefault("OTEL_LOGS_EXPORTER", "none")))
	protocol := pickProtocol("LOGS")
	logger.DebugContext(ctx, "initialize logger provider", "logs_exporter", kind)

	var exp sdklog.Exporter
	var err error
	if kind == "none" || kind == "" {
		return noop.NewLoggerProvider(), func(context.Context) error { return nil }, nil
	} else if kind == "console" {
		exp, err = stdoutlog.New()
	} else if kind == "otlp" && protocol == "grpc" {
		exp, err = otlploggrpc.New(ctx)
	} else if kind == "otlp" && strings.HasPrefix(protocol, "http") {
		exp, err = otlploghttp.New(ctx)
	} else {
		err = fmt.Errorf("unsupported logger exporter type or protocol: %s, %s", kind, protocol)
	}
	if err != nil {
		return nil, nil, err
	}

	lp := sdklog.NewLoggerProvider(
		sdklog.WithProcessor(sdklog.NewBatchProcessor(exp)),
		sdklog.WithResource(res),
	)
	return lp, lp.Shutdown, nil
}

func newTracerProvider(ctx context.Context, res *resource.Resource) (trace.TracerProvider, func(ctx context.Context) error, error) {
	kind := strings.ToLower(strings.TrimSpace(envOrDefault("OTEL_TRACES_EXPORTER", "none")))
	protocol := pickProtocol("TRACES")
	logger.DebugContext(ctx, "initialize tracer provider", "traces_exporter", kind)

	var exp sdktrace.SpanExporter
	var err error
	if kind == "none" || kind == "" {
		return tracenoop.NewTracerProvider(), func(context.Context) error { return nil }, nil
	} else if kind == "otlp" && protocol == "grpc" {
		exp, err = otlptracegrpc.New(ctx)
	} else if kind == "otlp" && strings.HasPrefix(protocol, "http") {
		exp, err = otlptracehttp.New(ctx)
	} else {
		err = fmt.Errorf("unsupported tracer exporter type or protocol: %s, %s", kind, protocol)
	}
	if err != nil {
		return nil, nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exp),
		sdktrace.WithResource(res),
	)
	return tp, tp.Shutdown, nil
}

func startPrometheusServer() (*http.Server, error) {
	host := strings.TrimSpace(envOrDefault("OTEL_EXPORTER_PROMETHEUS_HOST", "localhost"))
	port := strings.TrimSpace(envOrDefault("OTEL_EXPORTER_PROMETHEUS_PORT", "9464"))
	addr := net.JoinHostPort(host, port)
	logger.Debug("start prometheus server", "addr", addr)

	mux := http.NewServeMux()
	mux.Handle("/metrics", promhttp.Handler())

	srv := &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return nil, err
	}

	go func() {
		_ = srv.Serve(ln)
	}()

	return srv, nil
}

//nolint:cyclop // to be addressed in follow-up PR
func newMeterProvider(ctx context.Context, res *resource.Resource) (metric.MeterProvider, func(ctx context.Context) error, error) {
	kind := strings.ToLower(strings.TrimSpace(envOrDefault("OTEL_METRICS_EXPORTER", "memory")))
	protocol := pickProtocol("METRICS")
	logger.DebugContext(ctx, "initialize meter provider", "metrics_exporter", kind)

	var r sdkmetric.Reader
	var err error
	var shutdown func(ctx context.Context) error

	if kind == "memory" || kind == "none" || kind == "" {
		ManualReader = sdkmetric.NewManualReader()
		r = ManualReader
	} else if kind == "prometheus" {
		r, err = prometheus.New(prometheus.WithoutScopeInfo())
		if err == nil {
			server, serverErr := startPrometheusServer()
			if serverErr != nil {
				err = serverErr
			} else {
				shutdown = server.Shutdown
			}
		}
	} else if kind == "otlp" && protocol == "grpc" {
		var exp *otlpmetricgrpc.Exporter
		exp, err = otlpmetricgrpc.New(ctx)
		if err == nil {
			r = sdkmetric.NewPeriodicReader(exp)
		}
	} else if kind == "otlp" && strings.HasPrefix(protocol, "http") {
		var exp *otlpmetrichttp.Exporter
		exp, err = otlpmetrichttp.New(ctx)
		if err == nil {
			r = sdkmetric.NewPeriodicReader(exp)
		}
	} else {
		err = fmt.Errorf("unsupported meter exporter type or protocol: %s, %s", kind, protocol)
	}
	if err != nil {
		return nil, nil, err
	}

	mp := sdkmetric.NewMeterProvider(
		sdkmetric.WithResource(res),
		sdkmetric.WithReader(r),
	)
	if shutdown == nil {
		shutdown = mp.Shutdown
	} else {
		prevShutdown := shutdown
		shutdown = func(ctx context.Context) error {
			var firstErr error
			if err := prevShutdown(ctx); err != nil {
				logger.ErrorContext(ctx, "failed to shutdown meter provider", "err", err)
				if firstErr == nil {
					firstErr = err
				}
			}
			if err := mp.Shutdown(ctx); err != nil {
				logger.ErrorContext(ctx, "failed to shutdown meter provider", "err", err)
				if firstErr == nil {
					firstErr = err
				}
			}
			return firstErr
		}
	}
	return mp, shutdown, nil
}

func newResource(ctx context.Context, service, version string) (*resource.Resource, error) {
	r, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String(service),
			semconv.ServiceVersionKey.String(version),
		),
		resource.WithFromEnv(),
		resource.WithOS(),
		resource.WithHost(),
	)
	if err != nil {
		return nil, err
	}
	return r, nil
}

// Start initializes OpenTelemetry exporters, resources, and providers
// for logging, tracing, and metrics based on the standard OTEL_*
// environment variables:
// https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/
//
// This function should be called only once at the beginning of the program.
//
//nolint:cyclop // to be addressed in follow-up PR
func Start(ctx context.Context, service, version string) error {
	mu.Lock()
	defer mu.Unlock()
	if started {
		return errors.New("telemetry already started")
	}
	res, err := newResource(ctx, service, version)
	if err != nil {
		return fmt.Errorf("build resource: %w", err)
	}

	lp, loggerShutdown, err := newLoggerProvider(ctx, res)
	if err != nil {
		return fmt.Errorf("failed to create logger provider: %w", err)
	}
	logglobal.SetLoggerProvider(lp)

	logger = NewLogger("github.com/canonical/mayfly/internal/telemetry")

	tp, tracerShutdown, err := newTracerProvider(ctx, res)
	if err != nil {
		if err := loggerShutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "failed to shutdown logger provider", "error", err)
		}
		return fmt.Errorf("failed to create trace provider: %w", err)
	}
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{}, propagation.Baggage{},
	))

	mp, meterShutdown, err := newMeterProvider(ctx, res)
	if err != nil {
		if err := loggerShutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "failed to shutdown logger provider", "error", err)
		}
		if err := tracerShutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "failed to shutdown tracer provider", "error", err)
		}
		return fmt.Errorf("failed to create metric provider: %w", err)
	}
	otel.SetMeterProvider(mp)

	shutdown = func(ctx context.Context) error {
		var firstErr error
		if err := loggerShutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "failed to shutdown logger provider", "error", err)
			if firstErr == nil {
				firstErr = err
			}
		}
		if err := meterShutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "failed to shutdown meter provider", "error", err)
			if firstErr == nil {
				firstErr = err
			}
		}
		if err := tracerShutdown(ctx); err != nil {
			logger.ErrorContext(ctx, "failed to shutdown tracer provider", "error", err)
			if firstErr == nil {
				firstErr = err
			}
		}
		return firstErr
	}
	started = true
	return nil
}

// NewLogger creates a new slog.Logger. If OpenTelemetry logging is
// enabled, the logger is connected to the OpenTelemetry logging bridge.
func NewLogger(name string) *slog.Logger {
	if useOtelSlog() {
		return otelslog.NewLogger(name)
	}
	return slog.Default()
}

// Shutdown gracefully shutdown all OpenTelemetry exporters, providers
// that were previously enabled.
//
// Shutdown can be safely called before Start.
func Shutdown(ctx context.Context) error {
	mu.Lock()
	defer mu.Unlock()
	if shutdown == nil {
		return nil
	}
	err := shutdown(ctx)
	if err == nil {
		shutdown = nil
	}
	return err
}

type TestMetricReader struct {
	*sdkmetric.ManualReader
}

var testMetricReader *TestMetricReader
var testMetricReaderMutex sync.Mutex

// AcquireTestMetricReader initializes an in-memory metric reader for inspecting metric changes during tests.
// ReleaseTestMetricReader must be called after AcquireTestMetricReader.
func AcquireTestMetricReader(t *testing.T) *TestMetricReader {
	t.Helper()
	testMetricReaderMutex.Lock()
	if testMetricReader != nil {
		return testMetricReader
	}

	r := sdkmetric.NewManualReader(
		sdkmetric.WithTemporalitySelector(func(kind sdkmetric.InstrumentKind) metricdata.Temporality {
			return metricdata.DeltaTemporality
		}))
	mp := sdkmetric.NewMeterProvider(sdkmetric.WithReader(r))
	otel.SetMeterProvider(mp)

	testMetricReader = &TestMetricReader{ManualReader: r}
	testMetricReader.Collect(t)

	return testMetricReader
}

// ReleaseTestMetricReader releases the test metric reader lock.
func ReleaseTestMetricReader(t *testing.T) {
	t.Helper()
	testMetricReaderMutex.Unlock()
}

// Collect returns the accumulated metric changes and resets all metrics to zero.
func (m *TestMetricReader) Collect(t *testing.T) TestMetrics {
	t.Helper()

	var rm metricdata.ResourceMetrics
	err := m.ManualReader.Collect(t.Context(), &rm)
	if err != nil {
		t.Fatalf("failed to collect metrics: %v", err)
	}
	return TestMetrics{ResourceMetrics: &rm}
}

type TestMetrics struct {
	*metricdata.ResourceMetrics
}

// Counter returns the counter metric value that matches the provided name and attributes.
func (tm *TestMetrics) Counter(t *testing.T, name string, attrs ...attribute.KeyValue) float64 {
	t.Helper()

	var total float64
	for _, sm := range tm.ScopeMetrics {
		for _, m := range sm.Metrics {
			if m.Name != name {
				continue
			}
			switch data := m.Data.(type) {
			case metricdata.Sum[int64]:
				for _, dp := range data.DataPoints {
					if hasAttrs(dp.Attributes, attrs) {
						total += float64(dp.Value)
					}
				}
			case metricdata.Sum[float64]:
				for _, dp := range data.DataPoints {
					if hasAttrs(dp.Attributes, attrs) {
						total += dp.Value
					}
				}
			}
		}
	}
	return total
}

func hasAttrs(set attribute.Set, want []attribute.KeyValue) bool {
	if len(want) == 0 {
		return true
	}
	got := set.ToSlice()
	for _, w := range want {
		found := false
		for _, g := range got {
			if g.Key == w.Key && g.Value == w.Value {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}
