from __future__ import annotations

from fastapi import FastAPI

from .auth import IdentityAccessVerifier
from .config import Settings
from .errors import GatewayError, gateway_error_handler
from .routes import RouteRegistry, build_route_policies


def create_app(*, settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    app = FastAPI(title="IT Guardian Gateway Service", version="0.5.0-dev.1")
    app.state.settings = resolved
    app.state.route_registry = RouteRegistry(build_route_policies(resolved))
    app.state.identity_verifier = IdentityAccessVerifier(resolved)
    app.add_exception_handler(GatewayError, gateway_error_handler)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "service": resolved.service_name}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        # Gateway is stateless in v0.5. Readiness proves its local policy registry can
        # be constructed; downstream availability is handled per request and must not
        # create a startup dependency cycle.
        return {"status": "ready", "service": resolved.service_name}

    return app


app = create_app()
