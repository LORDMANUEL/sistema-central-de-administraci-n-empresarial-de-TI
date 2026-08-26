from __future__ import annotations

import logging

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class Publisher:
    async def publish(self, subject: str, payload: bytes, *, event_id: str) -> None:
        return None


def _settings() -> Settings:
    return Settings(
        identity_service_url="http://upstream.test",
        tenant_service_url="http://upstream.test",
        asset_service_url="http://upstream.test",
        enrollment_service_url="http://upstream.test",
        pki_service_url="http://upstream.test",
        audit_service_url="http://upstream.test",
    )


def test_metrics_endpoint_exposes_gateway_request_and_security_counters():
    async def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    app = create_app(
        settings=_settings(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        audit_publisher=Publisher(),
    )
    with TestClient(app) as client:
        client.get("/api/v1/ca/crl")
        metrics = client.get("/metrics")

    assert metrics.status_code == 200
    text = metrics.text
    for metric in (
        "guardian_gateway_requests_total",
        "guardian_gateway_auth_rejects_total",
        "guardian_gateway_route_rejects_total",
        "guardian_gateway_rate_limit_rejects_total",
        "guardian_gateway_upstream_latency_seconds",
        "guardian_gateway_audit_intent_failures_total",
        "guardian_gateway_completion_audit_failures_total",
    ):
        assert metric in text


def test_http_logs_never_include_authorization_or_request_body(caplog):
    async def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    app = create_app(
        settings=_settings(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        audit_publisher=Publisher(),
    )
    secret_body = "LOG-BODY-SECRET-MARKER"
    secret_auth = "LOG-AUTH-SECRET-MARKER"

    with caplog.at_level(logging.INFO, logger="guardian.gateway.http"):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "logger@example.com", "password": secret_body},
                headers={"Authorization": f"Bearer {secret_auth}"},
            )

    assert response.status_code == 200
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_body not in joined
    assert secret_auth not in joined
    assert "authorization" not in joined.lower()
    assert "password" not in joined.lower()
    assert "identity.login" in joined
