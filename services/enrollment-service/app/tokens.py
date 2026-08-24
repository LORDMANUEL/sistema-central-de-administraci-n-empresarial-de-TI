from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class PlainToken:
    plaintext: str
    token_hash: str
    hint: str


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_hint(value: str) -> str:
    if len(value) <= 12:
        return f"{value[:4]}..."
    return f"{value[:8]}...{value[-4:]}"


def generate_enrollment_token() -> PlainToken:
    plaintext = f"gdt_{secrets.token_urlsafe(32)}"
    return PlainToken(
        plaintext=plaintext,
        token_hash=hash_token(plaintext),
        hint=token_hint(plaintext),
    )


def request_fingerprint(
    *,
    tenant_id: str,
    asset_id: str,
    csr_sha256: str,
    platform: str,
    hostname: str,
    agent_version: str | None,
) -> str:
    canonical = {
        "tenant_id": tenant_id.strip(),
        "asset_id": asset_id.strip(),
        "csr_sha256": csr_sha256.strip().lower(),
        "platform": platform.strip().lower(),
        "hostname": hostname.strip().lower(),
        "agent_version": (agent_version or "").strip(),
    }
    payload = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
