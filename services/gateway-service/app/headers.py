from __future__ import annotations

import re
from collections.abc import Mapping
from uuid import uuid4


_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")


def normalize_request_id(value: str | None, *, max_length: int = 128) -> str:
    candidate = (value or "").strip()
    if (
        candidate
        and len(candidate) <= max_length
        and _REQUEST_ID_RE.fullmatch(candidate) is not None
    ):
        return candidate
    return str(uuid4())


def sanitize_inbound_headers(
    headers: Mapping[str, str],
    *,
    request_id: str,
    forward_authorization: bool,
) -> dict[str, str]:
    """Return headers safe to forward to a fixed upstream.

    Identity/tenant context is never accepted from caller-controlled Guardian headers.
    Forwarding metadata is rebuilt by trusted infrastructure in later deployment layers;
    v0.5 strips all caller-supplied Forwarded/X-Forwarded values.
    """

    outgoing: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower == "host" or lower == "forwarded" or lower == "x-request-id":
            continue
        if lower.startswith("x-forwarded-") or lower.startswith("x-guardian-"):
            continue
        if lower in _HOP_BY_HOP:
            continue
        if lower == "authorization" and not forward_authorization:
            continue
        outgoing[name] = value

    outgoing["X-Request-ID"] = request_id
    return outgoing


def sanitize_upstream_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    outgoing: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in _HOP_BY_HOP or lower in {"content-length", "x-request-id"}:
            continue
        if lower.startswith("x-guardian-") or lower == "forwarded" or lower.startswith("x-forwarded-"):
            continue
        outgoing[name] = value
    return outgoing
