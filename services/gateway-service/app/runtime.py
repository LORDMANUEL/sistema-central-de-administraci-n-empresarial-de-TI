from __future__ import annotations

import asyncio
import hashlib
import json
from time import monotonic
from urllib.parse import urlsplit

from fastapi import Request, Response

from .audit_publisher import GatewayAuditContext, execute_with_audit
from .auth import IdentityPrincipal, extract_bearer
from .errors import GatewayError
from .headers import normalize_request_id, sanitize_upstream_response_headers
from .limits import enforce_header_limit, read_bounded_body
from .logging import log_request
from .metrics import (
    AUDIT_INTENT_FAILURES,
    AUTH_REJECTS,
    COMPLETION_AUDIT_FAILURES,
    RATE_LIMIT_REJECTS,
    REQUESTS,
    UPSTREAM_LATENCY,
)
from .proxy import proxy_request_async
from .routes import AuthMode, RoutePolicy


def _json_object(body: bytes) -> dict:
    if not body:
        return {}
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _tenant_hint(request: Request, body: bytes) -> str | None:
    path_value = request.path_params.get("tenant_id")
    if isinstance(path_value, str) and path_value:
        return path_value
    query_value = request.query_params.get("tenant_id")
    if query_value:
        return query_value
    body_value = _json_object(body).get("tenant_id")
    if isinstance(body_value, str) and body_value:
        return body_value
    return None


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _hash_hint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _rate_key(
    policy: RoutePolicy,
    request: Request,
    body: bytes,
    principal: IdentityPrincipal | None,
    tenant_id: str | None,
) -> str:
    ip = _client_ip(request)
    if principal is not None:
        return f"user:{principal.user_id}:tenant:{tenant_id or 'platform'}"

    data = _json_object(body)
    if policy.rate_limit_bucket == "auth-login":
        email = data.get("email")
        if isinstance(email, str) and email.strip():
            return f"ip:{ip}:email:{_hash_hint(email.strip().lower())}"
    if policy.rate_limit_bucket == "endpoint-enrollment":
        token = data.get("token")
        if isinstance(token, str) and token:
            return f"ip:{ip}:token:{_hash_hint(token)}"
    return f"ip:{ip}"


def _upstream_name(policy: RoutePolicy) -> str | None:
    return urlsplit(policy.upstream_base_url).hostname


async def handle_gateway_request(request: Request, expected_route_id: str) -> Response:
    started = monotonic()
    status_code = 500
    principal: IdentityPrincipal | None = None
    upstream_name: str | None = None
    request_id = normalize_request_id(
        request.headers.get("x-request-id"),
        max_length=request.app.state.settings.max_request_id_length,
    )
    request.state.request_id = request_id

    try:
        matched = request.app.state.route_registry.require_northbound(
            request.method,
            request.url.path,
        )
        if matched.policy.route_id != expected_route_id:
            raise GatewayError(404, "gateway.route_not_allowed", "Route is not exposed by the Gateway")
        policy = matched.policy
        upstream_name = _upstream_name(policy)

        enforce_header_limit(dict(request.headers), request.app.state.settings.max_header_bytes)
        body = await read_bounded_body(request, policy.max_body_bytes)

        if policy.auth_mode == AuthMode.IDENTITY:
            try:
                bearer = extract_bearer(request.headers.get("authorization"))
                principal = await asyncio.to_thread(
                    request.app.state.identity_verifier.verify,
                    bearer,
                )
            except GatewayError:
                AUTH_REJECTS.inc()
                raise
        elif policy.auth_mode == AuthMode.INTERNAL_ONLY:
            raise GatewayError(404, "gateway.route_not_allowed", "Route is not exposed by the Gateway")

        tenant_id = _tenant_hint(request, body)
        rate_key = _rate_key(policy, request, body, principal, tenant_id)
        decision = request.app.state.rate_limiter.consume(
            policy.rate_limit_bucket,
            rate_key,
        )
        if not decision.allowed:
            RATE_LIMIT_REJECTS.labels(policy.rate_limit_bucket).inc()
            raise GatewayError(
                429,
                "gateway.rate_limited",
                "Too many requests",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )

        context = GatewayAuditContext(
            request_id=request_id,
            route_id=policy.route_id,
            method=policy.method,
            actor_user_id=principal.user_id if principal else None,
            tenant_id=tenant_id,
            client_ip=_client_ip(request),
        )

        async def upstream_call():
            with UPSTREAM_LATENCY.labels(policy.route_id).time():
                return await proxy_request_async(
                    request.app.state.http_client,
                    matched,
                    method=request.method,
                    query_string=request.scope.get("query_string", b""),
                    body=body,
                    headers=dict(request.headers),
                    request_id=request_id,
                )

        try:
            result = await execute_with_audit(
                policy,
                context,
                request.app.state.audit_publisher,
                upstream_call,
            )
        except GatewayError as exc:
            if exc.code == "gateway.audit_unavailable":
                AUDIT_INTENT_FAILURES.inc()
            raise

        if result.completion_audit_failed:
            COMPLETION_AUDIT_FAILURES.inc()

        status_code = result.response.status_code
        response_headers = sanitize_upstream_response_headers(dict(result.response.headers))
        response_headers["X-Request-ID"] = request_id
        return Response(
            content=result.response.content,
            status_code=result.response.status_code,
            headers=response_headers,
        )
    except GatewayError as exc:
        status_code = exc.status_code
        raise
    finally:
        REQUESTS.labels(expected_route_id, str(status_code)).inc()
        log_request(
            request_id=request_id,
            route_id=expected_route_id,
            method=request.method,
            status_code=status_code,
            duration_seconds=monotonic() - started,
            upstream_service=upstream_name,
            actor_user_id=principal.user_id if principal else None,
        )
