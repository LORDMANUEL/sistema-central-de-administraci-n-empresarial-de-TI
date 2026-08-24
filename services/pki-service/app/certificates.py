from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .errors import GuardianError


@dataclass(frozen=True)
class ValidatedCSR:
    csr: x509.CertificateSigningRequest
    csr_sha256: str


@dataclass(frozen=True)
class IssuedCertificate:
    certificate: x509.Certificate
    certificate_pem: str
    serial_hex: str
    fingerprint_sha256: str
    csr_sha256: str
    san_uri: str
    not_before: datetime
    not_after: datetime


def parse_and_validate_csr(csr_pem: str) -> ValidatedCSR:
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise GuardianError(422, "pki.invalid_csr", "Certificate signing request is invalid") from exc

    try:
        if not csr.is_signature_valid:
            raise GuardianError(422, "pki.invalid_csr", "Certificate signing request signature is invalid")
    except TypeError as exc:
        raise GuardianError(422, "pki.invalid_csr", "Certificate signing request signature is invalid") from exc

    public_key = csr.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        if public_key.key_size < 2048:
            raise GuardianError(422, "pki.weak_key", "RSA device keys must be at least 2048 bits")
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        if not isinstance(public_key.curve, (ec.SECP256R1, ec.SECP384R1)):
            raise GuardianError(422, "pki.weak_key", "EC device key curve is not allowed")
    else:
        raise GuardianError(422, "pki.weak_key", "Device public key type is not allowed")

    csr_der = csr.public_bytes(serialization.Encoding.DER)
    return ValidatedCSR(csr=csr, csr_sha256=hashlib.sha256(csr_der).hexdigest())


def _device_san_uri(tenant_id: str, asset_id: str, device_id: str) -> str:
    return (
        "spiffe://guardian/tenant/"
        f"{quote(tenant_id, safe='')}/asset/{quote(asset_id, safe='')}/device/{quote(device_id, safe='')}"
    )


def _device_key_usage(public_key) -> x509.KeyUsage:
    is_rsa = isinstance(public_key, rsa.RSAPublicKey)
    return x509.KeyUsage(
        digital_signature=True,
        content_commitment=False,
        key_encipherment=is_rsa,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=False,
        crl_sign=False,
        encipher_only=None,
        decipher_only=None,
    )


def issue_device_certificate(
    validated_csr: ValidatedCSR,
    *,
    signer_cert: x509.Certificate,
    signer_key,
    tenant_id: str,
    asset_id: str,
    device_id: str,
    platform: str,
    subject_cn: str,
    lifetime_days: int = 30,
    clock_skew_seconds: int = 120,
) -> IssuedCertificate:
    if not 1 <= lifetime_days <= 90:
        raise GuardianError(500, "pki.certificate_profile_invalid", "Certificate lifetime is outside policy")
    if not tenant_id or not asset_id or not device_id or not platform:
        raise GuardianError(422, "pki.certificate_identity_invalid", "Device certificate identity is incomplete")
    common_name = subject_cn.strip()
    if not common_name or len(common_name) > 255:
        raise GuardianError(422, "pki.certificate_identity_invalid", "Device certificate label is invalid")

    now = datetime.now(UTC)
    not_before = now - timedelta(seconds=clock_skew_seconds)
    requested_not_after = now + timedelta(days=lifetime_days)
    not_after = min(requested_not_after, signer_cert.not_valid_after_utc)
    if not_after <= now:
        raise GuardianError(503, "pki.ca_unavailable", "PKI signer certificate is expired")

    public_key = validated_csr.csr.public_key()
    san_uri = _device_san_uri(tenant_id, asset_id, device_id)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IT Guardian Devices"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(signer_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(_device_key_usage(public_key), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(san_uri)]),
            critical=False,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(signer_cert.public_key()),
            critical=False,
        )
        .sign(signer_key, hashes.SHA256())
    )

    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return IssuedCertificate(
        certificate=certificate,
        certificate_pem=certificate_pem,
        serial_hex=format(certificate.serial_number, "X"),
        fingerprint_sha256=certificate.fingerprint(hashes.SHA256()).hex(),
        csr_sha256=validated_csr.csr_sha256,
        san_uri=san_uri,
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
    )
