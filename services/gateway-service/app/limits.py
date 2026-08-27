from __future__ import annotations

from collections.abc import Mapping

from fastapi import Request

from .errors import GatewayError


def enforce_body_limit(body: bytes, max_body_bytes: int) -> None:
    if len(body) > max_body_bytes:
        raise GatewayError(413, "gateway.body_too_large", "Request body exceeds the route limit")


def enforce_header_limit(headers: Mapping[str, str], max_header_bytes: int) -> None:
    total = sum(len(str(name)) + len(str(value)) for name, value in headers.items())
    if total > max_header_bytes:
        raise GatewayError(431, "gateway.headers_too_large", "Request headers exceed the Gateway limit")


async def read_bounded_body(request: Request, max_body_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise GatewayError(400, "gateway.invalid_content_length", "Content-Length is invalid") from exc
        if declared < 0:
            raise GatewayError(400, "gateway.invalid_content_length", "Content-Length is invalid")
        if declared > max_body_bytes:
            raise GatewayError(413, "gateway.body_too_large", "Request body exceeds the route limit")

    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_body_bytes:
            raise GatewayError(413, "gateway.body_too_large", "Request body exceeds the route limit")
        chunks.append(chunk)
    return b"".join(chunks)
