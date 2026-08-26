from __future__ import annotations

from collections.abc import Mapping

from .errors import GatewayError


def enforce_body_limit(body: bytes, max_body_bytes: int) -> None:
    if len(body) > max_body_bytes:
        raise GatewayError(413, "gateway.body_too_large", "Request body exceeds the route limit")


def enforce_header_limit(headers: Mapping[str, str], max_header_bytes: int) -> None:
    total = sum(len(str(name)) + len(str(value)) for name, value in headers.items())
    if total > max_header_bytes:
        raise GatewayError(431, "gateway.headers_too_large", "Request headers exceed the Gateway limit")
