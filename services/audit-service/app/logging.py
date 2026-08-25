from __future__ import annotations

import json
import logging
from time import perf_counter

from fastapi import Request

from .metrics import HTTP_REQUESTS

logger = logging.getLogger("guardian.audit.http")


async def http_observability_middleware(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    duration_ms = (perf_counter() - started) * 1000.0

    route = request.scope.get("route")
    endpoint = request.scope.get("endpoint")
    path_template = getattr(route, "path", None) if endpoint is not None else None
    if not isinstance(path_template, str) or not path_template:
        path_template = "<unmatched>"

    request_id = getattr(request.state, "request_id", None) or response.headers.get("X-Request-ID", "unknown")
    HTTP_REQUESTS.labels(
        method=request.method,
        path=path_template,
        status=str(response.status_code),
    ).inc()

    # Deliberately never read request headers, query values, body, response body,
    # Authorization, cookies or raw unmatched path.
    record = {
        "duration_ms": round(duration_ms, 3),
        "event": "http_request",
        "method": request.method,
        "path": path_template,
        "request_id": request_id,
        "service": "audit-service",
        "status": response.status_code,
    }
    logger.info(json.dumps(record, separators=(",", ":"), sort_keys=True))
    return response
