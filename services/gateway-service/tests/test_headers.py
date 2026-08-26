from __future__ import annotations

from app.headers import normalize_request_id, sanitize_inbound_headers, sanitize_upstream_response_headers


def test_sanitize_headers_strips_spoofable_forwarded_hop_by_hop_and_host():
    incoming = {
        "Authorization": "Bearer admin-access-token",
        "Host": "evil.example",
        "X-Guardian-User": "attacker",
        "x-guardian-role": "platform_admin",
        "X-Guardian-Tenant": "other-tenant",
        "Forwarded": "for=203.0.113.9;proto=https",
        "X-Forwarded-For": "203.0.113.9",
        "X-Forwarded-Proto": "https",
        "Connection": "keep-alive",
        "Keep-Alive": "timeout=5",
        "Proxy-Authenticate": "Basic",
        "Proxy-Authorization": "Basic hidden",
        "TE": "trailers",
        "Trailer": "X-Test",
        "Transfer-Encoding": "chunked",
        "Upgrade": "websocket",
        "X-Request-ID": "caller-controlled",
        "User-Agent": "guardian-test",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    outgoing = sanitize_inbound_headers(
        incoming,
        request_id="srv-request-123",
        forward_authorization=True,
    )
    lowered = {key.lower(): value for key, value in outgoing.items()}

    assert lowered["authorization"] == "Bearer admin-access-token"
    assert lowered["x-request-id"] == "srv-request-123"
    assert lowered["user-agent"] == "guardian-test"
    assert lowered["accept"] == "application/json"
    assert lowered["content-type"] == "application/json"

    for forbidden in (
        "host",
        "x-guardian-user",
        "x-guardian-role",
        "x-guardian-tenant",
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-proto",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    ):
        assert forbidden not in lowered


def test_authorization_is_removed_when_policy_does_not_forward_credentials():
    outgoing = sanitize_inbound_headers(
        {"Authorization": "Bearer must-not-leak", "Accept": "application/json"},
        request_id="req-2",
        forward_authorization=False,
    )
    lowered = {key.lower(): value for key, value in outgoing.items()}
    assert "authorization" not in lowered
    assert lowered["accept"] == "application/json"
    assert lowered["x-request-id"] == "req-2"


def test_normalize_request_id_preserves_bounded_safe_values_and_replaces_unsafe_input():
    assert normalize_request_id("client-REQ_123:abc", max_length=128) == "client-REQ_123:abc"

    generated = normalize_request_id("../../bad request\nheader", max_length=128)
    assert generated != "../../bad request\nheader"
    assert len(generated) == 36

    too_long = normalize_request_id("x" * 129, max_length=128)
    assert len(too_long) == 36


def test_upstream_response_headers_cannot_override_gateway_owned_or_hop_by_hop_headers():
    sanitized = sanitize_upstream_response_headers(
        {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "Content-Length": "999999",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked",
            "X-Request-ID": "upstream-spoof",
            "X-Guardian-Role": "platform_admin",
        }
    )
    lowered = {key.lower(): value for key, value in sanitized.items()}

    assert lowered["content-type"] == "application/json"
    assert lowered["cache-control"] == "no-store"
    for forbidden in (
        "content-length",
        "connection",
        "transfer-encoding",
        "x-request-id",
        "x-guardian-role",
    ):
        assert forbidden not in lowered
