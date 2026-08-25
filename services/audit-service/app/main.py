from __future__ import annotations

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .database import build_engine, build_session_factory, database_ready
from .errors import GuardianError, guardian_error_handler, http_error_handler, request_id_middleware


def create_app(*, database_url: str | None = None) -> FastAPI:
    base = get_settings()
    settings = Settings(
        **{
            **base.model_dump(),
            **({"database_url": database_url} if database_url is not None else {}),
        }
    )
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    app = FastAPI(title="IT Guardian Audit Service", version="0.5.0-dev.1")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.middleware("http")(request_id_middleware)
    app.add_exception_handler(GuardianError, guardian_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            database_ready(engine)
        except Exception as exc:
            raise GuardianError(503, "audit.database_unavailable", "Audit database is unavailable") from exc
        return {"status": "ready", "service": settings.service_name}

    return app


app = create_app()
