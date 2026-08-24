import logging

from fastapi.testclient import TestClient

from app.main import create_app


def _app(tmp_path):
    return create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'pki-observability.db'}",
        ca_cert_path=str(tmp_path / "missing-cert.pem"),
        ca_key_path=str(tmp_path / "missing-key.pem"),
    )


def test_metrics_expose_http_and_pki_domain_counters(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        client.get("/health/live")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "it_guardian_pki_http_requests_total" in response.text
    assert "it_guardian_pki_certificates_issued_total" in response.text
    assert "it_guardian_pki_certificates_rotated_total" in response.text
    assert "it_guardian_pki_certificates_revoked_total" in response.text
    assert "it_guardian_pki_outbox_published_total" in response.text
    assert "it_guardian_pki_outbox_failed_total" in response.text


def test_request_id_is_preserved_and_returned(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "trace-pki-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-pki-123"


def test_http_logs_do_not_include_authorization_or_request_body(tmp_path, caplog):
    app = _app(tmp_path)
    auth_marker = "AUTH_MARKER_NOT_FOR_LOGS_123"
    body_marker = "BODY_MARKER_NOT_FOR_LOGS_456"

    with caplog.at_level(logging.INFO, logger="guardian.pki.http"):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/certificates/issue",
                headers={
                    "Authorization": f"Bearer {auth_marker}",
                    "X-Request-ID": "trace-sensitive-test",
                },
                json={
                    "issuance_id": "11111111-1111-1111-1111-111111111111",
                    "tenant_id": "tenant-1",
                    "asset_id": "asset-1",
                    "device_id": "device-1",
                    "platform": "windows",
                    "subject_cn": "WS-001",
                    "csr_pem": body_marker,
                },
            )

    assert response.status_code == 422
    logs = caplog.text
    assert "guardian.pki.http" in logs
    assert "POST" in logs
    assert "/api/v1/certificates/issue" in logs
    assert "trace-sensitive-test" in logs
    assert auth_marker not in logs
    assert body_marker not in logs
    assert "csr_pem" not in logs
