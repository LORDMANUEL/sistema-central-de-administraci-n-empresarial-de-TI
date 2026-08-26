from __future__ import annotations

import json
import logging

logger = logging.getLogger("guardian.gateway.http")


def log_request(
    *,
    request_id: str,
    route_id: str,
    method: str,
    status_code: int,
    duration_seconds: float,
    upstream_service: str | None,
    actor_user_id: str | None,
) -> None:
    payload: dict[str, object] = {
        "event": "gateway.http",
        "request_id": request_id,
        "route_id": route_id,
        "method": method,
        "status_code": int(status_code),
        "duration_ms": round(duration_seconds * 1000, 3),
    }
    if upstream_service:
        payload["upstream_service"] = upstream_service
    if actor_user_id:
        payload["actor_user_id"] = actor_user_id
    logger.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))
