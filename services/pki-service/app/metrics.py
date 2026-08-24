from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

HTTP_REQUESTS = Counter(
    "it_guardian_pki_http_requests_total",
    "Total HTTP requests handled by PKI Service",
    ["method", "path", "status"],
)
CERTIFICATES_ISSUED = Counter(
    "it_guardian_pki_certificates_issued_total",
    "Device certificates issued by PKI Service",
)
CERTIFICATES_ROTATED = Counter(
    "it_guardian_pki_certificates_rotated_total",
    "Device certificate rotations completed by PKI Service",
)
CERTIFICATES_REVOKED = Counter(
    "it_guardian_pki_certificates_revoked_total",
    "Device certificates revoked by PKI Service",
)
OUTBOX_PUBLISHED = Counter(
    "it_guardian_pki_outbox_published_total",
    "PKI outbox events acknowledged by the event bus",
)
OUTBOX_FAILED = Counter(
    "it_guardian_pki_outbox_failed_total",
    "PKI outbox publish attempts that failed",
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
