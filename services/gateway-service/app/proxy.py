from __future__ import annotations

import httpx

from .errors import GatewayError
from .headers import normalize_request_id, sanitize_inbound_headers
from .limits import enforce_body_limit
from .routes import AuthMode, RouteMatch


_RETRYABLE_METHODS = frozenset({"GET", "HEAD"})


def _build_url(matched: RouteMatch, query_string: bytes) -> str:
    base = matched.policy.upstream_base_url.rstrip("/")
    path = matched.upstream_path()
    url = f"{base}{path}"
    if query_string:
        try:
            query = query_string.decode("ascii")
        except UnicodeDecodeError as exc:
            raise GatewayError(400, "gateway.invalid_query", "Query string is invalid") from exc
        url = f"{url}?{query}"
    return url


def _prepare(
    matched: RouteMatch,
    *,
    method: str,
    query_string: bytes,
    body: bytes,
    headers: dict[str, str],
    request_id: str | None,
) -> tuple[str, str, dict[str, str], int]:
    policy = matched.policy
    method = method.upper()
    if method != policy.method:
        raise GatewayError(404, "gateway.route_not_allowed", "Route is not exposed by the Gateway")

    enforce_body_limit(body, policy.max_body_bytes)

    if request_id is None:
        incoming_request_id = None
        for key, value in headers.items():
            if key.lower() == "x-request-id":
                incoming_request_id = value
                break
        request_id = normalize_request_id(incoming_request_id)

    safe_headers = sanitize_inbound_headers(
        headers,
        request_id=request_id,
        forward_authorization=policy.auth_mode == AuthMode.IDENTITY,
    )
    url = _build_url(matched, query_string)
    max_attempts = 2 if method in _RETRYABLE_METHODS else 1
    return method, url, safe_headers, max_attempts


def proxy_request(
    client: httpx.Client,
    matched: RouteMatch,
    *,
    method: str,
    query_string: bytes,
    body: bytes,
    headers: dict[str, str],
    request_id: str | None = None,
) -> httpx.Response:
    method, url, safe_headers, max_attempts = _prepare(
        matched,
        method=method,
        query_string=query_string,
        body=body,
        headers=headers,
        request_id=request_id,
    )

    for attempt in range(max_attempts):
        try:
            return client.request(
                method,
                url,
                content=body if body else None,
                headers=safe_headers,
                timeout=matched.policy.timeout_seconds,
            )
        except httpx.ConnectError as exc:
            if attempt + 1 < max_attempts:
                continue
            raise GatewayError(502, "gateway.upstream_unavailable", "Upstream service is unavailable") from exc
        except httpx.TimeoutException as exc:
            raise GatewayError(504, "gateway.upstream_timeout", "Upstream service timed out") from exc
        except httpx.RequestError as exc:
            raise GatewayError(502, "gateway.upstream_unavailable", "Upstream request failed") from exc

    raise GatewayError(502, "gateway.upstream_unavailable", "Upstream service is unavailable")


async def proxy_request_async(
    client: httpx.AsyncClient,
    matched: RouteMatch,
    *,
    method: str,
    query_string: bytes,
    body: bytes,
    headers: dict[str, str],
    request_id: str | None = None,
) -> httpx.Response:
    method, url, safe_headers, max_attempts = _prepare(
        matched,
        method=method,
        query_string=query_string,
        body=body,
        headers=headers,
        request_id=request_id,
    )

    for attempt in range(max_attempts):
        try:
            return await client.request(
                method,
                url,
                content=body if body else None,
                headers=safe_headers,
                timeout=matched.policy.timeout_seconds,
            )
        except httpx.ConnectError as exc:
            if attempt + 1 < max_attempts:
                continue
            raise GatewayError(502, "gateway.upstream_unavailable", "Upstream service is unavailable") from exc
        except httpx.TimeoutException as exc:
            raise GatewayError(504, "gateway.upstream_timeout", "Upstream service timed out") from exc
        except httpx.RequestError as exc:
            raise GatewayError(502, "gateway.upstream_unavailable", "Upstream request failed") from exc

    raise GatewayError(502, "gateway.upstream_unavailable", "Upstream service is unavailable")
