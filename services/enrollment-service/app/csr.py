from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from .errors import GuardianError


@dataclass(frozen=True)
class ValidatedCSR:
    csr: x509.CertificateSigningRequest
    csr_sha256: str


def validate_csr(csr_pem: str) -> ValidatedCSR:
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise GuardianError(422, "enrollment.invalid_csr", "Certificate signing request is invalid") from exc

    try:
        if not csr.is_signature_valid:
            raise GuardianError(422, "enrollment.invalid_csr", "Certificate signing request signature is invalid")
    except TypeError as exc:
        raise GuardianError(422, "enrollment.invalid_csr", "Certificate signing request signature is invalid") from exc

    public_key = csr.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        if public_key.key_size < 2048:
            raise GuardianError(422, "enrollment.weak_key", "RSA device keys must be at least 2048 bits")
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        if not isinstance(public_key.curve, (ec.SECP256R1, ec.SECP384R1)):
            raise GuardianError(422, "enrollment.weak_key", "EC device key curve is not allowed")
    else:
        raise GuardianError(422, "enrollment.weak_key", "Device public key type is not allowed")

    csr_der = csr.public_bytes(serialization.Encoding.DER)
    return ValidatedCSR(
        csr=csr,
        csr_sha256=hashlib.sha256(csr_der).hexdigest(),
    )
