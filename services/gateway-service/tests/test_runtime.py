from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.auth import IdentityAccessVerifier
from app.config import Settings
from app.main import create_app
from app.rate_limit import BucketPolicy, TokenBucketLimiter, default_bucket_policies


class Publisher:
    def __init__(self, *, fail_accepted: bool = False) -> None:
        self.fail_accepted = fail_accepted
        self.items: list[tuple[str, dict]] = []

    async def publish(self, subject: str, payload: bytes, *, event_id: str) -> None:
        if self.fail_accepted and subject == "guardian.gateway.request.accepted":
            raise RuntimeError("NATS unavailable")
        self.items.append((subject, json.loads(payload)))


def _settings() -> Settings:
    return Settings(
        identity_service_url="http://upstream.test",
        tenant_service_url="http://upstream.test",
        asset_service_url="http://upstream.test",
        enrollment_service_url="http://upstream.test",
        pki_service_url="http://upstream.test",
        audit_service_url="http://upstream.test",
    )


def _verifier() -> tuple[IdentityAccessVerifier, str]:
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    kid = "runtime-ed25519"
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
                "alg": "EdDSA",
                "use": "sig",
                "kid": kid,
            }
        ]
    }
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "urn:it-guardian:identity",
            "aud": "it-guardian-services",
            "type": "access",
            "sub": "runtime-admin",
            "role": "platform_admin",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": str(uuid4()),
        },
        private,
        algorithm="EdDSA",
        headers={"kid": kid},
    )
    return IdentityAccessVerifier(_settings(), jwks=jwks), token


def test_identity_mutation_uses_real_gateway_pipeline_and_strips_spoofed_headers():
    seen: list[httpx.Request] = []

    async def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": "user-created"}, request=request)

    verifier, token = _verifier()
    publisher = Publisher()
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    app = create_app(
        settings=_settings(),
        identity_verifier=verifier,
        http_client=http_client,
        audit_publisher=publisher,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/users",
            json={"email": "new@example.com", "password": "BODY-SECRET-MARKER", "role": "viewer"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Guardian-Role": "platform_admin",
                "X-Guardian-Tenant": "spoofed",
                "Forwarded": "for=203.0.113.55",
                "X-Request-ID": "client-safe-request-1",
            },
        )

    assert response.status_code == 201
    assert response.headers["x-request-id"] == "client-safe-request-1"
    assert len(seen) == 1
    lowered = {key.lower(): value for key, value in seen[0].headers.items()}
    assert lowered["authorization"] == f"Bearer {token}"
    assert "x-guardian-role" not in lowered
    assert "x-guardian-tenant" not in lowered
    assert "forwarded" not in lowered
    assert [subject for subject, _ in publisher.items] == [
        "guardian.gateway.request.accepted",
        "guardian.gateway.request.completed",
    ]


def test_required_audit_failure_returns_503_before_upstream():
    calls = 0

    async def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(201, request=request)

    verifier, token = _verifier()
    app = create_app(
        settings=_settings(),
        identity_verifier=verifier,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        audit_publisher=Publisher(fail_accepted=True),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/users",
            json={"email": "blocked@example.com", "password": "x", "role": "viewer"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "gateway.audit_unavailable"
    assert calls == 0


def test_rate_limit_returns_429_with_retry_after_without_second_upstream_call():
    calls = 0

    async def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": "x"}, request=request)

    policies = default_bucket_policies()
    policies["auth-login"] = BucketPolicy(capacity=1, refill_per_second=0.01)
    limiter = TokenBucketLimiter(policies)
    app = create_app(
        settings=_settings(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        audit_publisher=Publisher(),
        rate_limiter=limiter,
    )
    with TestClient(app) as client:
        first = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "x"})
        second = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "x"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert 1 <= int(second.headers["retry-after"]) <= 3600
    assert calls == 1


def test_endpoint_enrollment_body_limit_returns_413_before_upstream():
    calls = 0

    async def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    app = create_app(
        settings=_settings(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
        audit_publisher=Publisher(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/enrollments",
            content=b"x" * (256 * 1024 + 1),
            headers={"Content-Type": "application/octet-stream"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "gateway.body_too_large"
    assert calls == 0


def test_unknown_and_internal_only_routes_return_stable_gateway_404():
    app = create_app(settings=_settings(), audit_publisher=Publisher())
    with TestClient(app) as client:
        unknown = client.get("/api/v1/not-real")
        internal = client.get("/api/v1/tenants/t-1/access")

    for response in (unknown, internal):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "gateway.route_not_allowed"
