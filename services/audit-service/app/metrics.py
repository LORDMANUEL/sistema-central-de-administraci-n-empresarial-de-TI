from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

HTTP_REQUESTS = Counter(
    "it_guardian_audit_http_requests_total",
    "Total HTTP requests handled by Audit Service",
    ["method", "path", "status"],
)
EVENTS_RECEIVED = Counter(
    "it_guardian_audit_events_received_total",
    "Guardian JetStream events received by Audit consumer",
)
EVENTS_INSERTED = Counter(
    "it_guardian_audit_events_inserted_total",
    "New immutable audit records committed",
)
EVENTS_DUPLICATE = Counter(
    "it_guardian_audit_events_duplicate_total",
    "Duplicate source event IDs safely deduplicated",
)
EVENTS_FAILED = Counter(
    "it_guardian_audit_events_failed_total",
    "Audit event ingestion attempts that failed without ACK",
)
CHAIN_VERIFICATION_FAILURES = Counter(
    "it_guardian_audit_chain_verification_failures_total",
    "Audit chain verification requests that detected inconsistency",
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
