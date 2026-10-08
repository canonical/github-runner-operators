# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""OWASP-compliant security event logger for the garm charm.

Single source of truth for the ``appid`` used in every security event and in the
Sigma detection rules under ``docs/security/sigma/garm/`` (logsource.product).
Import ``owasp_log`` wherever a security event occurs; never re-instantiate it.
"""

import atexit
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from owasp_logger import OWASPLogger
from owasp_logger.model import NESTED_JSON_KEY, OWASPLogEvent, OWASPLogMetadata

APPID = "canonical.garm"

logger = logging.getLogger(__name__)

# Dedicated logger carrying only OWASP security events, so an OTLP forwarding handler can be
# attached to the security feed without also exporting unrelated charm logs.
_SECURITY_LOGGER = logging.getLogger("canonical.garm.security")


class _UTCOWASPLogger(OWASPLogger):
    """OWASP logger that renders event timestamps in UTC.

    The upstream logger stamps events with ``datetime.now(timezone.utc).astimezone()``,
    which renders in the host's local UTC offset. OWASP requires UTC-aligned security
    timestamps, so emit RFC3339 UTC ("...Z") regardless of the host timezone.
    """

    def _log_event(self, event: str, level: int, metadata: OWASPLogMetadata) -> None:
        """Emit an OWASP event envelope with a UTC-rendered timestamp."""
        log = OWASPLogEvent(
            datetime=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            type="security",
            appid=self.appid,
            event=event,
            level=logging.getLevelName(level),
            **metadata,
        )
        self.logger.log(
            level,
            log.to_json(nested_json_key=NESTED_JSON_KEY),
            extra={NESTED_JSON_KEY: log.to_dict()},
        )


owasp_log = _UTCOWASPLogger(appid=APPID, logger=_SECURITY_LOGGER)


def configure_otlp_forwarding(endpoint: str) -> None:
    """Forward charm-emitted OWASP security events to an OTLP collector.

    Security events raised from charm hooks are emitted by the charm's Python process, not the
    workload container, so the ``go-framework`` Loki ``LogForwarder`` (which only tails workload
    logs) never sees them. When the garm-configurator relation supplies an OTLP collector
    endpoint — the same endpoint used to forward runner-host logs — attach an OpenTelemetry
    handler so these events are exported over OTLP/gRPC to that collector, which forwards them on
    to Loki.

    Idempotent, and a no-op when ``endpoint`` is empty or the OpenTelemetry export stack is
    unavailable.

    Args:
        endpoint: OTLP collector endpoint advertised by the garm-configurator relation, as an
            ``http(s)`` URL or a bare ``host:port``, or empty to skip forwarding.
    """
    if not endpoint:
        return
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        logger.warning(
            "OpenTelemetry export stack unavailable; security events stay in juju-log only"
        )
        return

    if any(isinstance(handler, LoggingHandler) for handler in _SECURITY_LOGGER.handlers):
        return

    target, insecure = _otlp_target_and_security(endpoint)
    provider = LoggerProvider(resource=Resource.create({"service.name": APPID}))
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=target, insecure=insecure))
    )
    set_logger_provider(provider)
    _SECURITY_LOGGER.addHandler(LoggingHandler(logger_provider=provider))
    atexit.register(provider.shutdown)


def _otlp_target_and_security(endpoint: str) -> tuple[str, bool]:
    """Resolve a configurator ``otel_collector_endpoint`` to a gRPC target and TLS mode.

    The garm-configurator contract advertises an ``http(s)`` URL, but the OTLP/gRPC exporter
    wants a bare ``host:port`` target plus a separate ``insecure`` flag. Derive the flag from the
    scheme — ``https`` uses TLS (the exporter supplies its default credentials), while ``http`` or
    a bare ``host:port`` stays plaintext — so an ``https`` collector is never forced onto a
    plaintext channel and silently dropped.

    Args:
        endpoint: The advertised endpoint, an ``http(s)`` URL or a bare ``host:port``.

    Returns:
        The gRPC target (``host:port``) and whether the channel must be plaintext.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme in ("http", "https"):
        return parsed.netloc, parsed.scheme == "http"
    return endpoint, True
