from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.errors import GatewayError
from app.proxy import proxy_request
from app.routes import RouteRegistry, build_route_policies


def _registry() -> RouteRegistry:
    return RouteRegistry(build_route_policies(Settings()))


def test_oversize_body_is_rejected_before_transport_is_called():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"unexpected": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    matched = _registry().require_northbound("POST", "/api/v1/enrollments")
    body = b"x" * (matched.policy.max_body_bytes + 1)

    with pytest.raises(GatewayError) as raised:
        proxy_request(
            client,
            matched,
            method="POST",
            query_string=b"",
            body=body,
            headers={"Content-Type": "application/json"},
        )

    assert raised.value.status_code == 413
    assert raised.value.code == "gateway.body_too_large"
    assert calls == 0


def test_mutating_request_is_attempted_exactly_once_on_connection_failure():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connect failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    matched = _registry().require_northbound("POST", "/api/v1/users")

    with pytest.raises(GatewayError) as raised:
        proxy_request(
            client,
            matched,
            method="POST",
            query_string=b"",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )

    assert raised.value.status_code == 502
    assert raised.value.code == "gateway.upstream_unavailable"
    assert calls == 1


def test_get_retries_once_only_on_connect_failure_before_response():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connect failed", request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    matched = _registry().require_northbound("GET", "/api/v1/assets")

    response = proxy_request(
        client,
        matched,
        method="GET",
        query_string=b"tenant_id=t-1",
        body=b"",
        headers={"Authorization": "Bearer x"},
    )

    assert response.status_code == 200
    assert calls == 2


def test_5xx_response_is_not_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "upstream"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    matched = _registry().require_northbound("GET", "/api/v1/assets")
    response = proxy_request(
        client,
        matched,
        method="GET",
        query_string=b"tenant_id=t-1",
        body=b"",
        headers={},
    )

    assert response.status_code == 503
    assert calls == 1


def test_proxy_target_is_derived_only_from_route_policy_and_path_params():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    matched = _registry().require_northbound("GET", "/api/v1/assets/asset-123")
    response = proxy_request(
        client,
        matched,
        method="GET",
        query_string=b"view=summary",
        body=b"",
        headers={"Host": "attacker.invalid"},
    )

    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0].url.host == "asset-service"
    assert seen[0].url.path == "/api/v1/assets/asset-123"
    assert seen[0].url.query == b"view=summary"
