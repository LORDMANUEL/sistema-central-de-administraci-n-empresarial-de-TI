from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

HTTP_REQUESTS = Counter(
    "it_guardian_enrollment_http_requests_total",
    "Total HTTP requests handled by Enrollment Service",
    ["method", "path", "status"],
)
TOKENS_CREATED = Counter(
    "it_guardian_enrollment_tokens_created_total",
    "Enrollment tokens created",
)
TOKENS_REVOKED = Counter(
    "it_guardian_enrollment_tokens_revoked_total",
    "Enrollment tokens revoked",
)
ENROLLMENT_SUCCESS = Counter(
    "it_guardian_enrollment_success_total",
    "Successful device enrollments",
)
ENROLLMENT_FAILURE = Counter(
    "it_guardian_enrollment_failure_total",
    "Deterministic device enrollment failures",
)
PKI_REQUESTS = Counter(
    "it_guardian_enrollment_pki_requests_total",
    "PKI issuance HTTP attempts made by Enrollment Service",
)
PKI_SUCCESS = Counter(
    "it_guardian_enrollment_pki_success_total",
    "PKI issuance requests completed successfully",
)
PKI_FAILURE = Counter(
    "it_guardian_enrollment_pki_failure_total",
    "PKI issuance operations that did not complete successfully",
)
OUTBOX_PUBLISHED = Counter(
    "it_guardian_enrollment_outbox_published_total",
    "Enrollment outbox events acknowledged by JetStream",
)
OUTBOX_FAILED = Counter(
    "it_guardian_enrollment_outbox_failed_total",
    "Enrollment outbox publish attempts that failed",
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
