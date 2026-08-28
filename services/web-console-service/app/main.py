from fastapi import FastAPI

from .api.resources import router as resources_router
from .api.session import router as session_router
from .config import Settings
from .errors import ConsoleError, console_error_handler
from .gateway import GatewayClient
from .session import SessionStore


def create_app(*, settings: Settings | None = None, gateway=None) -> FastAPI:
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

    @app.on_event("shutdown")
    def close_gateway():
        close = getattr(app.state.gateway, "close", None)
        if close is not None:
            close()

    return app


app = create_app()
