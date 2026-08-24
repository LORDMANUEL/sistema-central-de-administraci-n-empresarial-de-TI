from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class GuardianError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def response(request: Request, status_code: int, code: str, message: str, details=None):
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": _request_id(request),
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


async def request_id_middleware(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
    result = await call_next(request)
    result.headers["X-Request-ID"] = request.state.request_id
    return result


async def guardian_error_handler(request: Request, exc: GuardianError):
    return response(request, exc.status_code, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"loc": list(item.get("loc", ())), "type": item.get("type"), "message": item.get("msg")}
        for item in exc.errors()
    ]
    return response(request, 422, "tenant.validation_error", "Request validation failed", details)


async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return response(request, 404, "common.not_found", "Resource not found")
    return response(request, exc.status_code, "common.http_error", str(exc.detail))
