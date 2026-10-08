"""Monitoring and observability setup with Sentry and Prometheus."""

import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Callable

import sentry_sdk
from fastapi import FastAPI, Request
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

logger = logging.getLogger(__name__)

# Prometheus metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

active_requests = Gauge("active_requests", "Number of active requests")

etl_runs_total = Counter("etl_runs_total", "Total ETL runs", ["status"])

data_validation_failures = Counter(
    "data_validation_failures_total",
    "Total data validation failures",
    ["validation_type"],
)

db_connection_pool_size = Gauge(
    "db_connection_pool_size", "Database connection pool size"
)

sentry_privacy_excluded_total = Counter(
    "sentry_privacy_excluded_total", "Sentry payloads refused by the local privacy policy", ["kind"]
)

# Final SDK hooks receive serialized dictionaries. Rebuild only bounded
# operational metadata: key-name blacklists cannot sanitize arbitrary secrets.
_METHODS = frozenset({'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'CONNECT', 'TRACE'})
_LEVELS = frozenset({'debug', 'info', 'warning', 'error', 'fatal'})
_OPS = frozenset({'http.client', 'http.server', 'db', 'db.sql.query', 'function',
    'middleware.starlette', 'middleware.starlette.receive', 'middleware.starlette.send', 'subprocess'})
_STATUSES = frozenset({'ok', 'unknown_error', 'invalid_argument', 'deadline_exceeded', 'not_found',
    'already_exists', 'permission_denied', 'resource_exhausted', 'failed_precondition', 'aborted',
    'out_of_range', 'unimplemented', 'internal_error', 'unavailable', 'data_loss', 'unauthenticated', 'cancelled'})
_ERROR_TYPES = frozenset({'Exception', 'RuntimeError', 'ValueError', 'TypeError', 'KeyError',
    'OSError', 'TimeoutError', 'AssertionError', 'HTTPException', 'RequestValidationError',
    'ValidationError', 'OperationalError', 'IntegrityError', 'SocialError', 'CipherError', 'RecoveryError'})


class _UnsafeTelemetry(ValueError):
    """No input or exception detail is retained in a policy refusal."""


def _bounded_payload(value):
    pending, active, nodes, text_characters = [(value, 0, False)], set(), 0, 0
    while pending:
        item, depth, finished = pending.pop()
        if finished:
            active.remove(id(item))
            continue
        nodes += 1
        if nodes > 8192 or depth > 16:
            raise _UnsafeTelemetry()
        kind = type(item)
        if kind is dict or kind is list:
            if id(item) in active or len(item) > (256 if type(item) is dict else 1000):
                raise _UnsafeTelemetry()
            active.add(id(item))
            pending.append((item, depth, True))
            if type(item) is dict:
                if any(type(key) is not str or len(key) > 128 for key in item):
                    raise _UnsafeTelemetry()
                pending.extend((child, depth + 1, False) for child in item.values())
            else:
                pending.extend((child, depth + 1, False) for child in item)
        elif issubclass(kind, str):
            # SDK serializers retain string enums such as TransactionSource.
            # Their text is bounded here, then discarded; output choices below
            # accept only exact strings and fixed enumerations.
            length = str.__len__(item)
            text_characters += length
            if length > 65536 or text_characters > 524288:
                raise _UnsafeTelemetry()
        elif kind is float:
            if not math.isfinite(item):
                raise _UnsafeTelemetry()
        elif not any(kind is allowed for allowed in (type(None), bool, int, datetime)):
            raise _UnsafeTelemetry()


def _mapping(value):
    if type(value) is not dict:
        raise _UnsafeTelemetry()
    return value


def _items(value, maximum):
    if type(value) is not list or len(value) > maximum:
        raise _UnsafeTelemetry()
    return value


def _timestamp(value):
    if type(value) is str and len(value) <= 48:
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if type(value) is datetime:
        if value.tzinfo is not None and type(value.tzinfo) is not timezone and type(value.tzinfo) is not ZoneInfo:
            raise _UnsafeTelemetry()
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        value = value.timestamp()
    if (type(value) is not int and type(value) is not float) or not math.isfinite(value) or not 0 <= value <= 253402300799:
        raise _UnsafeTelemetry()
    return value


def _identity(value, length):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{' + str(length) + '}', value) is None:
        raise _UnsafeTelemetry()
    return value


def _known(value, choices):
    return type(value) is str and value in choices


def _timing_ids(value):
    result = {}
    for key, length in (('trace_id', 32), ('span_id', 16), ('parent_span_id', 16)):
        if value.get(key) is not None:
            result[key] = _identity(value[key], length)
    for key in ('timestamp', 'start_timestamp'):
        if key in value:
            result[key] = _timestamp(value[key])
    if 'start_timestamp' in result and 'timestamp' in result and result['timestamp'] < result['start_timestamp']:
        raise _UnsafeTelemetry()
    if 'op' in value:
        result['op'] = value['op'] if _known(value['op'], _OPS) else 'operation'
    if 'status' in value and _known(value['status'], _STATUSES):
        result['status'] = value['status']
    return result


def _http_status(value, *, allow_text=False):
    # Older SDKs serialize the HTTP status tag as decimal text. Accept that
    # exact representation only at the tag boundary; data/context fields are
    # integers. Never coerce arbitrary objects, booleans or private strings.
    if allow_text and type(value) is str and re.fullmatch(r'[1-5][0-9]{2}', value):
        value = int(value)
    if type(value) is not int or not 100 <= value <= 599:
        raise _UnsafeTelemetry()
    return value


def _http_metadata(value):
    value, result = _mapping(value), {}
    for key in ('method', 'http.method'):
        if key in value and _known(value[key], _METHODS):
            result[key] = value[key]
    status = None
    for key in ('status_code', 'http.status_code', 'http.response.status_code'):
        if key in value:
            candidate = _http_status(value[key])
            if status is not None and candidate != status:
                raise _UnsafeTelemetry()
            status = candidate
            result[key] = status
    return result


def _status_tags(value):
    value, result = _mapping(value), {}
    if 'http.status_code' in value:
        result['http.status_code'] = str(_http_status(value['http.status_code'], allow_text=True))
    if _known(value.get('status'), _STATUSES):
        result['status'] = value['status']
    return result


def _stacktrace(value):
    frames = _items(_mapping(value).get('frames', []), 256)
    result = []
    for frame in frames:
        frame = _mapping(frame)
        safe = {'filename': '[redacted]', 'function': '[redacted]'}
        if 'lineno' in frame:
            if type(frame['lineno']) is not int or not 1 <= frame['lineno'] <= 1000000:
                raise _UnsafeTelemetry()
            safe['lineno'] = frame['lineno']
        if type(frame.get('in_app')) is bool:
            safe['in_app'] = frame['in_app']
        result.append(safe)
    return {'frames': result}


def _breadcrumb(value):
    value = _mapping(value)
    result = {'type': 'default', 'category': 'redacted', 'message': 'Details excluded by privacy policy.'}
    if _known(value.get('type'), {'http', 'default', 'navigation', 'error', 'debug', 'query', 'user'}):
        result['type'] = value['type']
    if _known(value.get('level'), _LEVELS):
        result['level'] = value['level']
    if 'timestamp' in value:
        result['timestamp'] = _timestamp(value['timestamp'])
    if 'data' in value:
        result['data'] = _http_metadata(value['data'])
    return result


def before_breadcrumb_filter(breadcrumb, hint):
    """Discard free-form messages/data before they enter SDK scope storage."""
    try:
        _bounded_payload(breadcrumb)
        return _breadcrumb(breadcrumb)
    except (_UnsafeTelemetry, ValueError, TypeError, OverflowError):
        sentry_privacy_excluded_total.labels(kind='breadcrumb').inc()
        return None


def setup_sentry(app: FastAPI, dsn: str = None):
    """Configure Sentry for error tracking."""
    dsn = dsn or os.getenv("SENTRY_DSN")

    if not dsn:
        logger.warning("Sentry DSN not configured. Error tracking disabled.")
        return

    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        # Profiles are separate envelope items, outside the final payload hooks.
        profiles_sample_rate=0.0,
        environment=os.getenv("ENVIRONMENT", "production"),
        release=os.getenv("APP_VERSION", "1.0.0"),
        send_default_pii=False,  # Don't send PII
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size='never',
        before_send=before_send_filter,
        before_send_transaction=before_send_filter,
        before_breadcrumb=before_breadcrumb_filter,
    )

    logger.info("Sentry initialized successfully")


def before_send_filter(event, hint):
    """One fail-closed final projection for SDK error events and transactions.

    No URLs, arbitrary text, headers, SQL, user fields, vars or source context
    are forwarded. A hex identity is SDK correlation metadata, not authority.
    SDK hooks run after serialization; this does not protect upstream exporters.
    """
    try:
        _bounded_payload(event)
        event = _mapping(event)
        result = {'event_id': _identity(event.get('event_id'), 32), 'platform': 'python',
                  'message': 'Details excluded by privacy policy.'}
        if _known(event.get('level'), _LEVELS):
            result['level'] = event['level']
        if 'timestamp' in event:
            result['timestamp'] = _timestamp(event['timestamp'])
        if 'type' in event:
            if not _known(event['type'], {'transaction'}):
                raise _UnsafeTelemetry()
            result.update(type='transaction', transaction='Redacted operation', transaction_info={'source': 'custom'})
            result.update(_timing_ids(event))
        if 'request' in event:
            result['request'] = _http_metadata(event['request'])
        if 'tags' in event:
            result['tags'] = _status_tags(event['tags'])
        if 'contexts' in event:
            contexts, safe_contexts = _mapping(event['contexts']), {}
            if 'trace' in contexts:
                trace = _mapping(contexts['trace'])
                safe_contexts['trace'] = _timing_ids(trace)
                if 'data' in trace:
                    safe_contexts['trace']['data'] = _http_metadata(trace['data'])
            if 'response' in contexts:
                safe_contexts['response'] = _http_metadata(contexts['response'])
            if safe_contexts:
                result['contexts'] = safe_contexts
        if 'exception' in event:
            values = _items(_mapping(event['exception']).get('values', []), 20)
            result['exception'] = {'values': []}
            for value in values:
                value = _mapping(value)
                safe = {'type': value.get('type') if _known(value.get('type'), _ERROR_TYPES) else 'Error',
                        'value': 'Details excluded by privacy policy.'}
                if 'stacktrace' in value:
                    safe['stacktrace'] = _stacktrace(value['stacktrace'])
                result['exception']['values'].append(safe)
        if 'stacktrace' in event:
            result['stacktrace'] = _stacktrace(event['stacktrace'])
        if 'threads' in event:
            threads = _items(_mapping(event['threads']).get('values', []), 20)
            result['threads'] = {'values': []}
            for thread in threads:
                thread, safe = _mapping(thread), {}
                for key in ('current', 'crashed'):
                    if type(thread.get(key)) is bool:
                        safe[key] = thread[key]
                if 'stacktrace' in thread:
                    safe['stacktrace'] = _stacktrace(thread['stacktrace'])
                result['threads']['values'].append(safe)
        if 'breadcrumbs' in event:
            crumbs = _items(_mapping(event['breadcrumbs']).get('values', []), 100)
            result['breadcrumbs'] = {'values': [_breadcrumb(value) for value in crumbs]}
        if 'spans' in event:
            result['spans'] = []
            for value in _items(event['spans'], 1000):
                value = _mapping(value)
                safe = _timing_ids(value)
                if 'data' in value:
                    safe['data'] = _http_metadata(value['data'])
                if 'tags' in value:
                    safe['tags'] = _status_tags(value['tags'])
                result['spans'].append(safe)
        return result
    except (_UnsafeTelemetry, ValueError, TypeError, OverflowError):
        # Fixed labels only; never log the input or exception and recapture it.
        # The SDK additionally records lost events when this final hook refuses.
        sentry_privacy_excluded_total.labels(kind='event').inc()
        return None


def setup_prometheus(app: FastAPI):
    """Configure Prometheus metrics collection."""
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )

    instrumentator.instrument(app).expose(app, endpoint="/metrics")

    logger.info("Prometheus metrics enabled at /metrics")


async def metrics_middleware(request: Request, call_next: Callable):
    """Custom middleware for detailed metrics collection."""
    # Track active requests
    active_requests.inc()

    # Start timer
    start_time = time.time()

    try:
        # Process request
        response = await call_next(request)

        # Record metrics
        duration = time.time() - start_time
        http_request_duration_seconds.labels(
            method=request.method, endpoint=request.url.path
        ).observe(duration)

        http_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()

        return response

    finally:
        # Decrement active requests
        active_requests.dec()


def setup_structured_logging():
    """Configure structured JSON logging for production."""
    from pythonjsonlogger import jsonlogger

    log_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d"
    )
    log_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("Structured JSON logging configured")


def record_etl_run(status: str):
    """Record ETL run metrics."""
    etl_runs_total.labels(status=status).inc()


def record_validation_failure(validation_type: str):
    """Record data validation failure."""
    data_validation_failures.labels(validation_type=validation_type).inc()


def update_db_pool_metrics(pool_status: dict):
    """Update database connection pool metrics."""
    db_connection_pool_size.set(pool_status.get("size", 0))
