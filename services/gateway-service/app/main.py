from __future__ import annotations

from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from .audit_publisher import AuditEventPublisher, NatsJetStreamAuditPublisher
from .auth import IdentityAccessVerifier
from .config import Settings
from .errors import GatewayError, gateway_error_handler
from .headers import normalize_request_id
from .metrics import ROUTE_REJECTS, render_metrics
from .rate_limit import TokenBucketLimiter, default_bucket_policies
from .routes import AuthMode, RouteRegistry
from .runtime import handle_gateway_request
from .v06_routes import build_v06_route_policies


def create_app(*, settings: Settings | None = None, identity_verifier: IdentityAccessVerifier | None = None, http_client: httpx.AsyncClient | None = None, audit_publisher: AuditEventPublisher | None = None, rate_limiter: TokenBucketLimiter | None = None) -> FastAPI:
    resolved = settings or Settings()
    route_registry = RouteRegistry(build_v06_route_policies(resolved))
    owned_http_client = http_client is None
    owned_audit_publisher = audit_publisher is None
    resolved_http_client = http_client or httpx.AsyncClient()
    resolved_audit_publisher = audit_publisher or NatsJetStreamAuditPublisher(resolved.nats_url, resolved.nats_stream, connect_timeout_seconds=resolved.nats_connect_timeout_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try: yield
        finally:
            if owned_http_client: await app.state.http_client.aclose()
            if owned_audit_publisher: await app.state.audit_publisher.close()

    app = FastAPI(title="IT Guardian Gateway Service", version="0.6.0-dev.1", lifespan=lifespan)
    app.state.settings = resolved
    app.state.route_registry = route_registry
    app.state.identity_verifier = identity_verifier or IdentityAccessVerifier(resolved)
    app.state.http_client = resolved_http_client
    app.state.audit_publisher = resolved_audit_publisher
    app.state.rate_limiter = rate_limiter or TokenBucketLimiter(default_bucket_policies())
    app.add_exception_handler(GatewayError, gateway_error_handler)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = normalize_request_id(request.headers.get("x-request-id"), max_length=resolved.max_request_id_length)
        request.state.request_id = request_id
        if exc.status_code in {404, 405}:
            ROUTE_REJECTS.inc()
            return JSONResponse(status_code=404, headers={"X-Request-ID": request_id}, content={"error": {"code": "gateway.route_not_allowed", "message": "Route is not exposed by the Gateway", "request_id": request_id}})
        return JSONResponse(status_code=exc.status_code, headers={"X-Request-ID": request_id}, content={"error": {"code": "gateway.http_error", "message": "HTTP request failed", "request_id": request_id}})

    @app.get("/health/live")
    def health_live(): return {"status": "ok", "service": resolved.service_name}

    @app.get("/health/ready")
    def health_ready(): return {"status": "ready", "service": resolved.service_name}

    @app.get("/metrics")
    def metrics():
        payload, content_type = render_metrics()
        return Response(content=payload, headers={"Content-Type": content_type})

    def endpoint_for(route_id: str):
        async def endpoint(request: Request) -> Response: return await handle_gateway_request(request, route_id)
        endpoint.__name__ = f"gateway_{route_id.replace('.', '_').replace('-', '_')}"
        return endpoint

    for policy in route_registry.policies:
        if policy.auth_mode == AuthMode.INTERNAL_ONLY: continue
        app.add_api_route(policy.path_template, endpoint_for(policy.route_id), methods=[policy.method], name=policy.route_id)
    return app


app = create_app()
