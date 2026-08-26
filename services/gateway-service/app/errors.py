from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class GatewayError(Exception):
    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        },
    )
