from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from . import models as _models  # noqa: F401
from .api import router
from .auth import AccessTokenVerifier
from .config import Settings, get_settings
from .database import Base, build_engine, build_session_factory
from .errors import GuardianError, guardian_error_handler
from .metrics import HTTP_REQUESTS, render_metrics
from .tenant_client import TenantAccessClient


def create_app(*, database_url: str | None = None, auth_disabled: bool = False) -> FastAPI:
    settings = get_settings() if database_url is None else Settings(database_url=database_url)
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)

    app = FastAPI(title="IT Guardian Asset Service", version="0.3.0-dev.1")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.auth_disabled = auth_disabled
    app.state.auth = AccessTokenVerifier(settings)
    app.state.tenant_access_client = TenantAccessClient(
        settings.tenant_service_url,
        timeout_seconds=settings.tenant_access_timeout_seconds,
    )
    app.state.tenant_access_resolver = None
    app.state.tenant_reference_validator = None
    app.add_exception_handler(GuardianError, guardian_error_handler)
    app.include_router(router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        HTTP_REQUESTS.labels(request.method, request.url.path, str(response.status_code)).inc()
        return response

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise GuardianError(503, "asset.database_unavailable", "Asset database is unavailable") from exc
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    return app


app = create_app()