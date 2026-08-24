from __future__ import annotations

from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Response

from .api import router
from .auth import IdentityAccessVerifier
from .config import Settings, get_settings
from .database import build_engine, build_session_factory, database_ready
from .errors import GuardianError, guardian_error_handler, request_id_middleware
from .grants import EnrollmentGrantVerifier
from .metrics import render_metrics
from .rotation_api import router as rotation_router
from .tenant_client import TenantAccessClient


def _signer_ready(cert_path: str, key_path: str) -> None:
    try:
        cert_bytes = Path(cert_path).read_bytes()
        key_bytes = Path(key_path).read_bytes()
        certificate = x509.load_pem_x509_certificate(cert_bytes)
        private_key = serialization.load_pem_private_key(key_bytes, password=None)
        cert_public = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_public = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if cert_public != key_public:
            raise ValueError("certificate and private key do not match")
    except Exception as exc:
        raise GuardianError(503, "pki.ca_unavailable", "PKI online signing material is unavailable") from exc


def create_app(
    *,
    database_url: str | None = None,
    ca_cert_path: str | None = None,
    ca_key_path: str | None = None,
) -> FastAPI:
    base = get_settings()
    settings = Settings(
        **{
            **base.model_dump(),
            **({"database_url": database_url} if database_url is not None else {}),
            **({"ca_cert_path": ca_cert_path} if ca_cert_path is not None else {}),
            **({"ca_key_path": ca_key_path} if ca_key_path is not None else {}),
        }
    )
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    app = FastAPI(title="IT Guardian PKI Service", version="0.4.0-dev.1")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.root_cert_path = settings.root_cert_path
    app.state.grant_verifier = EnrollmentGrantVerifier(settings)
    app.state.identity_verifier = IdentityAccessVerifier(settings)
    app.state.tenant_access_client = TenantAccessClient(
        settings.tenant_service_url,
        timeout_seconds=settings.tenant_access_timeout_seconds,
    )
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(GuardianError, guardian_error_handler)
    app.include_router(router)
    app.include_router(rotation_router)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            database_ready(engine)
        except Exception as exc:
            raise GuardianError(503, "pki.database_unavailable", "PKI database is unavailable") from exc
        _signer_ready(settings.ca_cert_path, settings.ca_key_path)
        return {"status": "ready", "service": settings.service_name}

    @app.get("/metrics")
    def metrics() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    return app


app = create_app()
