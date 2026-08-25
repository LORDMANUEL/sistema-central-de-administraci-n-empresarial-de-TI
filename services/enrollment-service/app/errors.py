from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from .logging import log_http_request
from .metrics import HTTP_REQUESTS


class GuardianError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id

    route = request.scope.get("route")
    path_template = getattr(route, "path", request.url.path)
    HTTP_REQUESTS.labels(request.method, path_template, str(response.status_code)).inc()
    log_http_request(
        request,
        response,
        request_id=request.state.request_id,
        duration_ms=(perf_counter() - started) * 1000,
        path_template=path_template,
    )
    return response


async def guardian_error_handler(request: Request, exc: GuardianError) -> JSONResponse:
    response = JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id(request),
            }
        },
    )
    response.headers["X-Request-ID"] = request_id(request)
    return response
