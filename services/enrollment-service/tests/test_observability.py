import base64
import logging

from fastapi.testclient import TestClient

from app.main import create_app


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


def _app(tmp_path):
    return create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'observability.db'}",
        signing_key=_seed(),
    )


def test_metrics_expose_http_and_enrollment_domain_counters(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        client.get("/health/live")
        response = client.get("/metrics")

    assert response.status_code == 200
    for metric in (
        "it_guardian_enrollment_http_requests_total",
        "it_guardian_enrollment_tokens_created_total",
        "it_guardian_enrollment_tokens_revoked_total",
        "it_guardian_enrollment_success_total",
        "it_guardian_enrollment_failure_total",
        "it_guardian_enrollment_pki_requests_total",
        "it_guardian_enrollment_pki_success_total",
        "it_guardian_enrollment_pki_failure_total",
        "it_guardian_enrollment_outbox_published_total",
        "it_guardian_enrollment_outbox_failed_total",
    ):
        assert metric in response.text


def test_request_id_is_preserved_and_returned(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "trace-enrollment-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-enrollment-123"


def test_http_logs_do_not_include_authorization_token_csr_or_request_body(tmp_path, caplog):
    app = _app(tmp_path)
    auth_marker = "AUTH_MARKER_NOT_FOR_LOGS_123"
    token_marker = "TOKEN_MARKER_NOT_FOR_LOGS_456"
    csr_marker = "CSR_MARKER_NOT_FOR_LOGS_789"

    with caplog.at_level(logging.INFO, logger="guardian.enrollment.http"):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/enrollments",
                headers={
                    "Authorization": f"Bearer {auth_marker}",
                    "X-Request-ID": "trace-sensitive-enrollment",
                },
                json={
                    "token": token_marker,
                    "platform": "windows",
                    "hostname": "WS-001",
                    "csr_pem": csr_marker,
                },
            )

    assert response.status_code == 422
    logs = caplog.text
    assert "guardian.enrollment.http" in logs
    assert "POST" in logs
    assert "/api/v1/enrollments" in logs
    assert "trace-sensitive-enrollment" in logs
    assert auth_marker not in logs
    assert token_marker not in logs
    assert csr_marker not in logs
    assert "csr_pem" not in logs
