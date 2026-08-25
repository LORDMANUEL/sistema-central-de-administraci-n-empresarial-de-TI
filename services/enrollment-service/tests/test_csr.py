import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from app.csr import validate_csr
from app.errors import GuardianError


def _csr_pem(key, common_name="device-1") -> str:
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _pem_from_der(der: bytes) -> str:
    encoded = base64.b64encode(der).decode("ascii")
    lines = [encoded[index : index + 64] for index in range(0, len(encoded), 64)]
    return "-----BEGIN CERTIFICATE REQUEST-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE REQUEST-----\n"


@pytest.mark.parametrize(
    "key",
    [
        pytest.param(rsa.generate_private_key(public_exponent=65537, key_size=2048), id="rsa-2048"),
        pytest.param(ec.generate_private_key(ec.SECP256R1()), id="p256"),
        pytest.param(ec.generate_private_key(ec.SECP384R1()), id="p384"),
    ],
)
def test_supported_csr_profiles_are_accepted(key):
    validated = validate_csr(_csr_pem(key))
    assert validated.csr.is_signature_valid is True
    assert len(validated.csr_sha256) == 64


def test_malformed_or_tampered_csr_is_rejected():
    with pytest.raises(GuardianError) as raised:
        validate_csr("not-a-csr")
    assert raised.value.code == "enrollment.invalid_csr"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.load_pem_x509_csr(_csr_pem(key).encode("ascii"))
    der = bytearray(csr.public_bytes(serialization.Encoding.DER))
    der[-1] ^= 0x01
    with pytest.raises(GuardianError) as raised:
        validate_csr(_pem_from_der(bytes(der)))
    assert raised.value.code == "enrollment.invalid_csr"


def test_weak_rsa_and_unsupported_ec_curve_are_rejected():
    weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    with pytest.raises(GuardianError) as raised:
        validate_csr(_csr_pem(weak))
    assert raised.value.code == "enrollment.weak_key"

    unsupported = ec.generate_private_key(ec.SECP521R1())
    with pytest.raises(GuardianError) as raised:
        validate_csr(_csr_pem(unsupported))
    assert raised.value.code == "enrollment.weak_key"
