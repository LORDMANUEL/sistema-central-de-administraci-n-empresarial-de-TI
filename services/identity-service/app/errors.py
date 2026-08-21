from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class GuardianError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"error": error},
        headers={"X-Request-ID": request_id},
    )


async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


async def guardian_error_handler(request: Request, exc: GuardianError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Deliberately omit rejected input so secrets such as passwords are never echoed.
    details = [
        {
            "loc": list(error.get("loc", ())),
            "type": error.get("type", "validation_error"),
            "message": error.get("msg", "Invalid value"),
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status_code=422,
        code="identity.validation_error",
        message="Request validation failed",
        details=details,
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return _error_response(
            request,
            status_code=404,
            code="common.not_found",
            message="Resource not found",
        )
    return _error_response(
        request,
        status_code=exc.status_code,
        code="common.http_error",
        message=str(exc.detail) if exc.detail else "HTTP error",
    )
