from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class EventNormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedAuditEvent:
    tenant_id: str | None
    source_event_id: str
    source_type: str
    source_service: str
    actor_user_id: str | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    occurred_at: datetime
    metadata: dict[str, Any]


_FORBIDDEN_FRAGMENTS = (
    "authorization",
    "bearer",
    "password",
    "secret",
    "private_key",
    "privatekey",
    "signing_key",
    "signingkey",
    "seed",
    "csr",
    "token",
    "cookie",
)

_ALLOWED_METADATA_KEYS = frozenset(
    {
        "hostname",
        "platform",
        "agent_version",
        "site_id",
        "department_id",
        "certificate_id",
        "certificate_serial_hex",
        "provider",
        "external_id",
        "route_id",
        "method",
        "status_code",
        "client_ip",
        "reason_code",
        "role",
        "membership_role",
    }
)


def _normalized_key(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _forbidden_key(value: str) -> bool:
    key = _normalized_key(value)
    compact = key.replace("_", "")
    for fragment in _FORBIDDEN_FRAGMENTS:
        fragment_norm = fragment.replace("-", "_")
        if fragment_norm in key or fragment_norm.replace("_", "") in compact:
            return True
    return False


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _forbidden_key(str(key)) or _contains_forbidden_key(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _safe_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def sanitize_metadata(source_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    sanitized: dict[str, Any] = {}
    for key in _ALLOWED_METADATA_KEYS:
        if key not in data:
            continue
        value = data[key]
        if _forbidden_key(key) or _contains_forbidden_key(value):
            continue
        if not _safe_scalar(value):
            continue
        sanitized[key] = value
    return sanitized


def _source_service(event_type: str) -> str:
    if event_type.startswith("identity."):
        return "identity"
    if event_type.startswith("tenant."):
        return "tenant"
    if event_type.startswith("asset."):
        return "asset"
    if event_type.startswith("pki."):
        return "pki"
    if event_type.startswith("enrollment."):
        return "enrollment"
    if event_type in {"device.enrolled", "device.enrollment.failed"}:
        return "enrollment"
    if event_type.startswith("gateway."):
        return "gateway"
    prefix = event_type.split(".", 1)[0].strip()
    return prefix or "unknown"


def _parse_occurred_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EventNormalizationError("occurred_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventNormalizationError("occurred_at is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _required_string(envelope: dict[str, Any], key: str) -> str:
    value = envelope.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EventNormalizationError(f"{key} is required")
    return value.strip()


def normalize_event(envelope: dict[str, Any]) -> NormalizedAuditEvent:
    if not isinstance(envelope, dict):
        raise EventNormalizationError("event envelope must be an object")
    if envelope.get("schema_version") != 1:
        raise EventNormalizationError("unsupported schema_version")

    source_event_id = _required_string(envelope, "event_id")
    source_type = _required_string(envelope, "type")
    resource_type = _required_string(envelope, "aggregate_type")
    resource_id = _required_string(envelope, "aggregate_id")
    occurred_at = _parse_occurred_at(envelope.get("occurred_at"))

    data = envelope.get("data")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise EventNormalizationError("data must be an object")

    tenant_id = data.get("tenant_id")
    if tenant_id is not None and not isinstance(tenant_id, str):
        raise EventNormalizationError("tenant_id must be a string")

    actor_user_id = data.get("actor_user_id")
    if actor_user_id is not None and not isinstance(actor_user_id, str):
        actor_user_id = None
    actor_type = data.get("actor_type") if isinstance(data.get("actor_type"), str) else "system"
    action = data.get("action") if isinstance(data.get("action"), str) else source_type
    outcome = data.get("outcome") if isinstance(data.get("outcome"), str) else "success"
    request_id = data.get("request_id") if isinstance(data.get("request_id"), str) else None

    return NormalizedAuditEvent(
        tenant_id=tenant_id,
        source_event_id=source_event_id,
        source_type=source_type,
        source_service=_source_service(source_type),
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        request_id=request_id,
        occurred_at=occurred_at,
        metadata=sanitize_metadata(source_type, data),
    )
