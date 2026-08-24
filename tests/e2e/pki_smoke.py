from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import nats
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

PKI = "http://127.0.0.1:8000"
IDENTITY = "http://identity-service:8000"


def request(method: str, url: str, payload: dict[str, Any] | None = None, token: str | None = None) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type and raw:
                return response.status, json.loads(raw)
            return response.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw)
        except (ValueError, TypeError):
            detail = raw.decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def wait_ready(url: str, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _, body = request("GET", url)
            if isinstance(body, dict) and body.get("status") in {"ok", "ready"}:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Service did not become ready: {url}; last_error={last_error}")


def decode_seed(value: str) -> bytes:
    padding_text = "=" * ((4 - len(value) % 4) % 4)
    raw = base64.urlsafe_b64decode(value + padding_text)
    if len(raw) != 32:
        raise RuntimeError("Smoke Enrollment seed must decode to 32 bytes")
    return raw


def build_csr() -> tuple[ec.EllipticCurvePrivateKey, str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PKI-SMOKE-DEVICE")]))
        .sign(private_key, hashes.SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    csr_sha256 = hashlib.sha256(csr.public_bytes(serialization.Encoding.DER)).hexdigest()
    return private_key, csr_pem, csr_sha256


def build_enrollment_grant(
    private_key: Ed25519PrivateKey,
    *,
    tenant_id: str,
    asset_id: str,
    device_id: str,
    issuance_id: str,
    csr_sha256: str,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": "urn:it-guardian:enrollment",
            "aud": "it-guardian-pki",
            "type": "certificate_issue",
            "sub": device_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "issuance_id": issuance_id,
            "csr_sha256": csr_sha256,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=60)).timestamp()),
            "jti": str(uuid4()),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": "pki-smoke-enrollment-v1"},
    )


def verify_chain(leaf: x509.Certificate, chain: list[x509.Certificate]) -> None:
    assert len(chain) == 2, f"Expected intermediate + root, got {len(chain)} certificates"
    intermediate, root = chain
    intermediate.public_key().verify(
        leaf.signature,
        leaf.tbs_certificate_bytes,
        padding.PKCS1v15(),
        leaf.signature_hash_algorithm,
    )
    root.public_key().verify(
        intermediate.signature,
        intermediate.tbs_certificate_bytes,
        padding.PKCS1v15(),
        intermediate.signature_hash_algorithm,
    )
    root.public_key().verify(
        root.signature,
        root.tbs_certificate_bytes,
        padding.PKCS1v15(),
        root.signature_hash_algorithm,
    )


async def fetch_event(subject: str) -> dict:
    connection = await nats.connect("nats://nats:4222", connect_timeout=5)
    try:
        jetstream = connection.jetstream()
        subscription = await jetstream.pull_subscribe(subject)
        messages = await subscription.fetch(1, timeout=20)
        if not messages:
            raise AssertionError(f"No event received for {subject}")
        event = json.loads(messages[0].data)
        await messages[0].ack()
        return event
    finally:
        await connection.drain()


def main() -> None:
    wait_ready(f"{IDENTITY}/health/ready")
    wait_ready(f"{PKI}/health/ready")

    identity_email = "pki-smoke@example.com"
    identity_password = "Guardian-PKI-Smoke-2026!"
    status, _ = request(
        "POST",
        f"{IDENTITY}/api/v1/auth/bootstrap",
        {
            "email": identity_email,
            "display_name": "PKI Smoke Administrator",
            "password": identity_password,
        },
    )
    assert status == 201
    status, tokens = request(
        "POST",
        f"{IDENTITY}/api/v1/auth/login",
        {"email": identity_email, "password": identity_password},
    )
    assert status == 200
    admin_token = tokens["access_token"]

    seed = decode_seed(os.environ["PKI_SMOKE_ENROLLMENT_SEED"])
    enrollment_private_key = Ed25519PrivateKey.from_private_bytes(seed)
    device_private_key, csr_pem, csr_sha256 = build_csr()
    tenant_id = str(uuid4())
    asset_id = str(uuid4())
    device_id = str(uuid4())
    issuance_id = str(uuid4())
    grant = build_enrollment_grant(
        enrollment_private_key,
        tenant_id=tenant_id,
        asset_id=asset_id,
        device_id=device_id,
        issuance_id=issuance_id,
        csr_sha256=csr_sha256,
    )

    status, issued = request(
        "POST",
        f"{PKI}/api/v1/certificates/issue",
        {
            "issuance_id": issuance_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "platform": "windows",
            "subject_cn": "PKI-SMOKE-DEVICE",
            "csr_pem": csr_pem,
        },
        grant,
    )
    assert status == 201
    assert issued["status"] == "active"
    assert issued["issuance_id"] == issuance_id
    assert issued["tenant_id"] == tenant_id
    assert "PRIVATE KEY" not in json.dumps(issued)

    leaf = x509.load_pem_x509_certificate(issued["certificate_pem"].encode("ascii"))
    chain = x509.load_pem_x509_certificates(issued["ca_chain_pem"].encode("ascii"))
    verify_chain(leaf, chain)
    assert leaf.public_key().public_numbers() == device_private_key.public_key().public_numbers()

    status, listed = request(
        "GET",
        f"{PKI}/api/v1/certificates?tenant_id={tenant_id}",
        token=admin_token,
    )
    assert status == 200
    assert [item["certificate_id"] for item in listed] == [issued["certificate_id"]]

    status, revoked = request(
        "POST",
        f"{PKI}/api/v1/certificates/{issued['certificate_id']}/revoke",
        {"reason": "key_compromise"},
        admin_token,
    )
    assert status == 200
    assert revoked["status"] == "revoked"
    assert revoked["revocation_reason"] == "key_compromise"

    status, crl_pem = request("GET", f"{PKI}/api/v1/ca/crl")
    assert status == 200
    crl = x509.load_pem_x509_crl(crl_pem)
    intermediate = chain[0]
    intermediate.public_key().verify(
        crl.signature,
        crl.tbs_certlist_bytes,
        padding.PKCS1v15(),
        crl.signature_hash_algorithm,
    )
    assert leaf.serial_number in {entry.serial_number for entry in crl}

    issued_event = asyncio.run(fetch_event("guardian.pki.certificate.issued"))
    revoked_event = asyncio.run(fetch_event("guardian.pki.certificate.revoked"))
    assert issued_event["schema_version"] == 1
    assert issued_event["type"] == "pki.certificate.issued"
    assert issued_event["data"]["certificate_id"] == issued["certificate_id"]
    assert revoked_event["schema_version"] == 1
    assert revoked_event["type"] == "pki.certificate.revoked"
    assert revoked_event["data"]["certificate_id"] == issued["certificate_id"]

    print(
        json.dumps(
            {
                "status": "ok",
                "certificate_id": issued["certificate_id"],
                "serial_hex": issued["serial_hex"],
                "tenant_id": tenant_id,
                "events_verified": 2,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
