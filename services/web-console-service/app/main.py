import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.resources import router as resources_router
from .api.session import router as session_router
from .config import Settings
from .errors import ConsoleError, console_error_handler
from .gateway import GatewayClient
from .session import SessionStore


def create_app(*, settings: Settings | None = None, gateway=None, static_dir: str | Path | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="IT Guardian Web Console BFF", version="0.8.0-dev.1")
    app.state.settings = settings
    app.state.sessions = SessionStore(
        ttl_seconds=settings.session_ttl_seconds,
        max_sessions=settings.max_sessions,
    )
    app.state.gateway = gateway or GatewayClient(settings)
    app.add_exception_handler(ConsoleError, console_error_handler)
    app.include_router(session_router)
    app.include_router(resources_router)

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        response = app.state.gateway.request("GET", "/health/live")
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
    def close_gateway():
        close = getattr(app.state.gateway, "close", None)
        if close is not None:
            close()

    return app


app = create_app()
