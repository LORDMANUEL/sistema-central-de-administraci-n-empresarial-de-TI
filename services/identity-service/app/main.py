from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models as _models  # noqa: F401 - registers SQLAlchemy metadata
from .api import router
from .config import Settings, get_settings
from .database import Base, Database
from .errors import (
    GuardianError,
    guardian_error_handler,
    http_error_handler,
    request_id_middleware,
    validation_error_handler,
)
from .logging import install_http_logging
from .metrics import install_metrics
from .security import TokenService


def create_app(*, database_url: str | None = None, auto_create_schema: bool | None = None) -> FastAPI:
    settings = get_settings()
    if database_url is not None:
        settings = Settings(
            service_name=settings.service_name,
            environment=settings.environment,
            database_url=database_url,
            signing_key=settings.signing_key,
            jwt_key_id=settings.jwt_key_id,
            jwt_issuer=settings.jwt_issuer,
            jwt_audience=settings.jwt_audience,
            access_token_minutes=settings.access_token_minutes,
            refresh_token_days=settings.refresh_token_days,
        )

    database = Database(settings.database_url)
    should_auto_create = (database_url is not None) if auto_create_schema is None else auto_create_schema

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if should_auto_create:
            Base.metadata.create_all(database.engine)
        yield
        database.engine.dispose()

    app = FastAPI(
        title="IT Guardian Identity Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.tokens = TokenService(settings)
    app.middleware("http")(request_id_middleware)
    app.state.metrics = install_metrics(app)
    install_http_logging(app, settings.service_name)
    app.add_exception_handler(GuardianError, guardian_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.include_router(router)

    @app.get("/.well-known/jwks.json", include_in_schema=False)
    def jwks() -> dict[str, list[dict[str, str]]]:
        return app.state.tokens.jwks()

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": settings.service_name}

    @app.get("/health/ready")
    def health_ready(response: Response) -> dict[str, str]:
        try:
            database.is_ready()
        except Exception:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "error", "service": settings.service_name}
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
