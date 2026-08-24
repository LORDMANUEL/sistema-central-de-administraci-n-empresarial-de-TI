import base64
from datetime import UTC, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.ca import initialize_ca
from app.certificates import issue_device_certificate, parse_and_validate_csr
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
def test_supported_csrs_are_accepted(key):
    validated = parse_and_validate_csr(_csr_pem(key))
    assert validated.csr.is_signature_valid is True
    assert len(validated.csr_sha256) == 64


def test_csr_with_tampered_signature_is_rejected():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.load_pem_x509_csr(_csr_pem(key).encode("ascii"))
    der = bytearray(csr.public_bytes(serialization.Encoding.DER))
    der[-1] ^= 0x01
    tampered = _pem_from_der(bytes(der))

    with pytest.raises(GuardianError) as raised:
        parse_and_validate_csr(tampered)
    assert raised.value.code == "pki.invalid_csr"


def test_weak_rsa_and_unsupported_ec_curve_are_rejected():
    weak_rsa = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    with pytest.raises(GuardianError) as raised:
        parse_and_validate_csr(_csr_pem(weak_rsa))
    assert raised.value.code == "pki.weak_key"

    unsupported = ec.generate_private_key(ec.SECP521R1())
    with pytest.raises(GuardianError) as raised:
        parse_and_validate_csr(_csr_pem(unsupported))
    assert raised.value.code == "pki.weak_key"


def test_malformed_csr_is_rejected():
    with pytest.raises(GuardianError) as raised:
        parse_and_validate_csr("not-a-csr")
    assert raised.value.code == "pki.invalid_csr"


def test_issued_certificate_has_guardian_device_profile_and_valid_chain(tmp_path):
    paths = initialize_ca(tmp_path / "root", tmp_path / "online")
    signer_cert = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())
    signer_key = serialization.load_pem_private_key(paths.intermediate_key.read_bytes(), password=None)
    root_cert = x509.load_pem_x509_certificate(paths.root_cert.read_bytes())

    device_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    validated = parse_and_validate_csr(_csr_pem(device_key, "WS-SPS-001"))
    issued = issue_device_certificate(
        validated,
        signer_cert=signer_cert,
        signer_key=signer_key,
        tenant_id="tenant-1",
        asset_id="asset-1",
        device_id="device-1",
        platform="windows",
        subject_cn="WS-SPS-001",
        lifetime_days=30,
        clock_skew_seconds=120,
    )
    cert = issued.certificate

    signer_cert.public_key().verify(
        cert.signature,
        cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        cert.signature_hash_algorithm,
    )
    root_cert.public_key().verify(
        signer_cert.signature,
        signer_cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        signer_cert.signature_hash_algorithm,
    )

    assert cert.issuer == signer_cert.subject
    assert cert.public_key().public_numbers() == device_key.public_key().public_numbers()
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.digital_signature is True
    assert usage.key_encipherment is True
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.CLIENT_AUTH in eku
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.UniformResourceIdentifier) == [
        "spiffe://guardian/tenant/tenant-1/asset/asset-1/device/device-1"
    ]
    cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)

    lifetime = cert.not_valid_after_utc - cert.not_valid_before_utc
    assert timedelta(days=30) <= lifetime <= timedelta(days=30, minutes=3)
    assert issued.serial_hex == format(cert.serial_number, "X")
    assert issued.fingerprint_sha256 == cert.fingerprint(hashes.SHA256()).hex()
    assert x509.load_pem_x509_certificate(issued.certificate_pem.encode("ascii")) == cert
    assert issued.csr_sha256 == validated.csr_sha256
