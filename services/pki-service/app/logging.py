from __future__ import annotations

import json
import logging

from fastapi import Request, Response

logger = logging.getLogger("guardian.pki.http")


def log_http_request(
    request: Request,
    response: Response,
    *,
    request_id: str,
    duration_ms: float,
    path_template: str,
) -> None:
    record = {
        "event": "http_request",
        "service": "pki-service",
        "request_id": request_id,
        "method": request.method,
        "path": path_template,
        "status": response.status_code,
        "duration_ms": round(duration_ms, 3),
    }
    logger.info(json.dumps(record, separators=(",", ":"), sort_keys=True))
