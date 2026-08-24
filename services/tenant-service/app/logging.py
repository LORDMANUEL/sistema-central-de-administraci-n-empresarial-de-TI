import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

_http_logger = logging.getLogger("guardian.tenant.http")


def install_http_logging(app: FastAPI, service_name: str) -> None:
    @app.middleware("http")
    async def http_logging_middleware(request: Request, call_next):
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 3)
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        request_id = getattr(
            request.state,
            "request_id",
            request.headers.get("X-Request-ID") or str(uuid4()),
        )
        _http_logger.info(
            json.dumps(
                {
                    "service": service_name,
                    "request_id": request_id,
                    "method": request.method,
                    "path": route_path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return response
