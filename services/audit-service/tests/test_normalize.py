from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.normalize import EventNormalizationError, normalize_event, sanitize_metadata


def envelope(event_type: str = "device.enrolled", **data):
    return {
        "schema_version": 1,
        "event_id": "11111111-1111-1111-1111-111111111111",
        "type": event_type,
        "aggregate_type": "device",
        "aggregate_id": "22222222-2222-2222-2222-222222222222",
        "occurred_at": "2026-08-24T12:00:00Z",
        "data": {
            "tenant_id": "33333333-3333-3333-3333-333333333333",
            "hostname": "WS-001",
            "platform": "windows",
            **data,
        },
    }


def test_normalize_requires_versioned_guardian_envelope():
    bad = envelope()
    del bad["event_id"]
    with pytest.raises(EventNormalizationError):
        normalize_event(bad)

    bad_version = envelope()
    bad_version["schema_version"] = 99
    with pytest.raises(EventNormalizationError):
        normalize_event(bad_version)


def test_domain_event_is_normalized_without_copying_unknown_payload():
    event = envelope(
        agent_version="0.7.0",
        certificate_id="cert-1",
        unknown_sensitive_business_blob={"anything": "must-not-copy"},
    )
    normalized = normalize_event(event)
    assert normalized.source_event_id == event["event_id"]
    assert normalized.tenant_id == event["data"]["tenant_id"]
    assert normalized.source_type == "device.enrolled"
    assert normalized.source_service == "enrollment"
    assert normalized.resource_type == "device"
    assert normalized.resource_id == event["aggregate_id"]
    assert normalized.action == "device.enrolled"
    assert normalized.outcome == "success"
    assert normalized.occurred_at == datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    assert normalized.metadata == {
        "hostname": "WS-001",
        "platform": "windows",
        "agent_version": "0.7.0",
        "certificate_id": "cert-1",
    }


def test_gateway_event_uses_explicit_actor_action_outcome_and_safe_metadata():
    event = envelope(
        actor_user_id="user-9",
        actor_type="user",
        action="tenant.update",
        outcome="accepted",
        request_id="req-9",
        route_id="tenant.update",
        method="PATCH",
        status_code=202,
        client_ip="10.0.0.8",
        reason_code="policy-ok",
    )
    event["type"] = "gateway.request.accepted"
    event["aggregate_type"] = "gateway_request"
    event["aggregate_id"] = "req-9"
    normalized = normalize_event(event)
    assert normalized.source_service == "gateway"
    assert normalized.actor_user_id == "user-9"
    assert normalized.actor_type == "user"
    assert normalized.action == "tenant.update"
    assert normalized.outcome == "accepted"
    assert normalized.request_id == "req-9"
    assert normalized.metadata["route_id"] == "tenant.update"
    assert normalized.metadata["method"] == "PATCH"
    assert normalized.metadata["status_code"] == 202
    assert normalized.metadata["client_ip"] == "10.0.0.8"
    assert normalized.metadata["reason_code"] == "policy-ok"


@pytest.mark.parametrize(
    "key",
    [
        "Authorization",
        "bearer",
        "password",
        "client_secret",
        "private_key",
        "privateKey",
        "signing_key",
        "seed",
        "csr_pem",
        "token",
        "token_hash",
        "refresh_token",
        "access_token",
        "cookie",
        "set-cookie",
    ],
)
def test_forbidden_secret_key_fragments_are_never_persisted_recursively(key):
    data = {
        "hostname": "WS-001",
        "nested": {key: "SECRET-MARKER"},
        key: "SECRET-MARKER",
    }
    sanitized = sanitize_metadata("device.enrolled", data)
    rendered = repr(sanitized).lower()
    assert "secret-marker" not in rendered
    assert "nested" not in sanitized


def test_provider_external_id_and_location_references_are_allowlisted_when_expected():
    sanitized = sanitize_metadata(
        "asset.external_identity.linked",
        {
            "provider": "wazuh",
            "external_id": "agent-77",
            "site_id": "site-1",
            "department_id": "dept-1",
            "other": "drop-me",
        },
    )
    assert sanitized == {
        "provider": "wazuh",
        "external_id": "agent-77",
        "site_id": "site-1",
        "department_id": "dept-1",
    }
