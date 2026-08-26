from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "guardian_gateway_requests_total",
    "Gateway requests by route and status",
    ("route_id", "status"),
)
AUTH_REJECTS = Counter(
    "guardian_gateway_auth_rejects_total",
    "Gateway authentication rejects",
)
ROUTE_REJECTS = Counter(
    "guardian_gateway_route_rejects_total",
    "Gateway route rejects",
)
RATE_LIMIT_REJECTS = Counter(
    "guardian_gateway_rate_limit_rejects_total",
    "Gateway rate-limit rejects by bucket",
    ("bucket",),
)
UPSTREAM_LATENCY = Histogram(
    "guardian_gateway_upstream_latency_seconds",
    "Gateway upstream request latency",
    ("route_id",),
)
AUDIT_INTENT_FAILURES = Counter(
    "guardian_gateway_audit_intent_failures_total",
    "Required gateway audit-intent publish failures",
)
COMPLETION_AUDIT_FAILURES = Counter(
    "guardian_gateway_completion_audit_failures_total",
    "Gateway completion audit publish failures",
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
