from __future__ import annotations

from fastapi import FastAPI, Response

from .admin_api import router as admin_router
from .asset_client import AssetClient
from .auth import IdentityAccessVerifier
from .config import Settings, get_settings
from .database import build_engine, build_session_factory, database_ready
from .enrollment_api import router as enrollment_router
from .errors import GuardianError, guardian_error_handler, request_id_middleware
from .metrics import render_metrics
from .pki_client import PKIClient
from .signing import EnrollmentGrantSigner
from .tenant_client import TenantAccessClient


def create_app(*, database_url: str | None = None, signing_key: str | None = None) -> FastAPI:
    base = get_settings()
    settings = Settings(
        **{
            **base.model_dump(),
            **({"database_url": database_url} if database_url is not None else {}),
            **({"signing_key": signing_key} if signing_key is not None else {}),
        }
    )
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    signer = None
    signer_error = None
    try:
        signer = EnrollmentGrantSigner(settings)
    except GuardianError as exc:
        signer_error = exc

    app = FastAPI(title="IT Guardian Enrollment Service", version="0.4.0-dev.1")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.signer = signer
    app.state.signer_error = signer_error
    app.state.identity_verifier = IdentityAccessVerifier(settings)
    app.state.tenant_access_client = TenantAccessClient(
        settings.tenant_service_url,
        timeout_seconds=settings.downstream_timeout_seconds,
    )
    app.state.tenant_access_resolver = None
    app.state.asset_client = AssetClient(
        settings.asset_service_url,
        timeout_seconds=settings.downstream_timeout_seconds,
    )
    app.state.pki_client = PKIClient(
        settings.pki_service_url,
        timeout_seconds=settings.downstream_timeout_seconds,
        retry_attempts=settings.pki_retry_attempts,
    )
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(GuardianError, guardian_error_handler)
    app.include_router(admin_router)
    app.include_router(enrollment_router)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            database_ready(engine)
        except Exception as exc:
            raise GuardianError(503, "enrollment.database_unavailable", "Enrollment database is unavailable") from exc
        if app.state.signer is None:
            raise GuardianError(503, "enrollment.signer_unavailable", "Enrollment signing material is unavailable")
        return {"status": "ready", "service": settings.service_name}

    @app.get("/.well-known/jwks.json")
    def jwks() -> dict:
        if app.state.signer is None:
            raise GuardianError(503, "enrollment.signer_unavailable", "Enrollment signing material is unavailable")
        return app.state.signer.jwks()

    @app.get("/metrics")
    def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    return app


app = create_app()
