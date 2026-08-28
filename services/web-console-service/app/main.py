import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import redis

from .api.resources import router as resources_router
from .api.session import router as session_router
from .config import Settings
from .errors import ConsoleError, console_error_handler
from .gateway import GatewayClient
from .session import RedisSessionStore, SessionStore


def _session_store(settings: Settings):
    if settings.session_redis_url:
        client = redis.Redis.from_url(settings.session_redis_url, decode_responses=True)
        return RedisSessionStore(client, ttl_seconds=settings.session_ttl_seconds, max_sessions=settings.max_sessions)
    if settings.environment.lower() == "production":
        raise RuntimeError("WEB_CONSOLE_SESSION_REDIS_URL is required in production")
    return SessionStore(ttl_seconds=settings.session_ttl_seconds, max_sessions=settings.max_sessions)


def create_app(*, settings: Settings | None = None, gateway=None, static_dir: str | Path | None = None, session_store=None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="IT Guardian Web Console BFF", version="0.8.0-dev.1")
    app.state.settings = settings
    app.state.sessions = session_store or _session_store(settings)
    app.state.gateway = gateway or GatewayClient(settings)
    app.add_exception_handler(ConsoleError, console_error_handler)
    app.include_router(session_router)
    app.include_router(resources_router)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/console/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            if not app.state.sessions.ready():
                raise RuntimeError("session store unavailable")
            response = app.state.gateway.request("GET", "/health/live")
        except Exception as exc:
            raise ConsoleError(503, "console.dependency_not_ready", "Console dependency is not ready") from exc
        if response.status_code != 200:
            raise ConsoleError(503, "console.gateway_not_ready", "Gateway is not ready")
        return {"status": "ready"}

    root = Path(static_dir or os.getenv("WEB_CONSOLE_STATIC_DIR", "/app/static"))
    index = root / "index.html"
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/console/assets", StaticFiles(directory=assets), name="console-assets")

    if index.is_file():
        @app.get("/console", include_in_schema=False)
        @app.get("/console/{path:path}", include_in_schema=False)
        def console_spa(path: str = ""):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            return FileResponse(index, headers={"Cache-Control": "no-store"})

    @app.on_event("shutdown")
    def close_dependencies():
        close_gateway = getattr(app.state.gateway, "close", None)
        if close_gateway is not None:
            close_gateway()
        close_sessions = getattr(app.state.sessions, "close", None)
        if close_sessions is not None:
            close_sessions()

    return app


app = create_app()
