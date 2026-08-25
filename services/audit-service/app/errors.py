from __future__ import annotations

from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class GuardianError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def request_id_for(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if value:
        return value
    value = str(uuid4())
    request.state.request_id = value
    return value


async def request_id_middleware(request: Request, call_next):
    supplied = request.headers.get("x-request-id", "").strip()
    request.state.request_id = supplied[:128] if supplied and len(supplied) <= 128 else str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


async def guardian_error_handler(request: Request, exc: GuardianError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id_for(request),
            }
        },
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        code = "audit.not_found"
        message = "Resource not found"
    else:
        code = f"audit.http_{exc.status_code}"
        message = str(exc.detail) if isinstance(exc.detail, str) else "HTTP request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id_for(request),
            }
        },
    )
