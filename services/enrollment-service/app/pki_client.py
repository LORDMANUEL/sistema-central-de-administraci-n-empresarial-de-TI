from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from .errors import GuardianError


@dataclass(frozen=True)
class PKICertificateResult:
    certificate_id: str
    issuance_id: str
    tenant_id: str
    asset_id: str
    device_id: str
    serial_hex: str
    fingerprint_sha256: str
    certificate_pem: str
    ca_chain_pem: str
    not_before: datetime
    not_after: datetime


def _datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime field is not a string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PKIClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        retry_attempts: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = max(1, retry_attempts)

    def issue(
        self,
        *,
        grant: str,
        issuance_id: str,
        tenant_id: str,
        asset_id: str,
        device_id: str,
        platform: str,
        subject_cn: str,
        csr_pem: str,
    ) -> PKICertificateResult:
        request_body = {
            "issuance_id": issuance_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "platform": platform,
            "subject_cn": subject_cn,
            "csr_pem": csr_pem,
        }
        headers = {"Authorization": f"Bearer {grant}"}

        for _attempt in range(self.retry_attempts):
            try:
                response = httpx.post(
                    f"{self.base_url}/api/v1/certificates/issue",
                    headers=headers,
                    json=request_body,
                    timeout=self.timeout_seconds,
                )
            except httpx.HTTPError:
                continue

            if response.status_code in (200, 201):
                return self._parse_success(response, request_body)
            if response.status_code == 409:
                raise GuardianError(
                    409,
                    "enrollment.pki_issuance_conflict",
                    "PKI issuance ID conflicts with existing certificate data",
                )
            if 400 <= response.status_code < 500:
                raise GuardianError(
                    422,
                    "enrollment.pki_rejected",
                    "PKI rejected the certificate issuance request",
                )
            if response.status_code >= 500:
                continue

            raise GuardianError(
                503,
                "enrollment.pki_unavailable",
                "PKI Service returned an unexpected response",
            )

        raise GuardianError(
            503,
            "enrollment.pki_unavailable",
            "PKI Service is unavailable",
        )

    @staticmethod
    def _parse_success(response: httpx.Response, request_body: dict) -> PKICertificateResult:
        try:
            data = response.json()
            required = {
                "certificate_id": str(data["certificate_id"]),
                "issuance_id": str(data["issuance_id"]),
                "tenant_id": str(data["tenant_id"]),
                "asset_id": str(data["asset_id"]),
                "device_id": str(data["device_id"]),
                "serial_hex": str(data["serial_hex"]),
                "fingerprint_sha256": str(data["fingerprint_sha256"]),
                "certificate_pem": str(data["certificate_pem"]),
                "ca_chain_pem": str(data["ca_chain_pem"]),
            }
            not_before = _datetime(data["not_before"])
            not_after = _datetime(data["not_after"])
        except (ValueError, TypeError, KeyError) as exc:
            raise GuardianError(
                503,
                "enrollment.pki_invalid_response",
                "PKI Service response is invalid",
            ) from exc

        for key in ("issuance_id", "tenant_id", "asset_id", "device_id"):
            if required[key] != request_body[key]:
                raise GuardianError(
                    503,
                    "enrollment.pki_invalid_response",
                    "PKI Service response identity does not match the request",
                )

        if not all(required.values()) or len(required["fingerprint_sha256"]) != 64:
            raise GuardianError(
                503,
                "enrollment.pki_invalid_response",
                "PKI Service response is incomplete",
            )

        return PKICertificateResult(
            **required,
            not_before=not_before,
            not_after=not_after,
        )
