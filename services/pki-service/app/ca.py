from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID


class CAInitializationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CAPaths:
    root_key: Path
    root_cert: Path
    online_root_cert: Path
    intermediate_key: Path
    intermediate_cert: Path


def _paths(root_dir: Path, online_dir: Path) -> CAPaths:
    return CAPaths(
        root_key=root_dir / "root-ca-key.pem",
        root_cert=root_dir / "root-ca-cert.pem",
        online_root_cert=online_dir / "root-ca-cert.pem",
        intermediate_key=online_dir / "intermediate-ca-key.pem",
        intermediate_cert=online_dir / "intermediate-ca-cert.pem",
    )


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def _private_key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _name(common_name: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IT Guardian"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _ca_key_usage() -> x509.KeyUsage:
    return x509.KeyUsage(
        digital_signature=False,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=True,
        crl_sign=True,
        encipher_only=None,
        decipher_only=None,
    )


def _build_root(key: rsa.RSAPrivateKey, now: datetime) -> x509.Certificate:
    subject = _name("IT Guardian Root CA")
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(_ca_key_usage(), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )


def _build_intermediate(
    key: rsa.RSAPrivateKey,
    root_key: rsa.RSAPrivateKey,
    root_cert: x509.Certificate,
    now: datetime,
) -> x509.Certificate:
    return (
        x509.CertificateBuilder()
        .subject_name(_name("IT Guardian Device Intermediate CA"))
        .issuer_name(root_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(min(now + timedelta(days=1825), root_cert.not_valid_after_utc))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_ca_key_usage(), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256())
    )


def _public_bytes(public_key) -> bytes:
    return public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _verify_rsa_signature(issuer: x509.Certificate, subject: x509.Certificate) -> None:
    public_key = issuer.public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise CAInitializationError("CA issuer key is not RSA")
    public_key.verify(
        subject.signature,
        subject.tbs_certificate_bytes,
        padding.PKCS1v15(),
        subject.signature_hash_algorithm,
    )


def _validate_existing(paths: CAPaths) -> None:
    try:
        root_key = serialization.load_pem_private_key(paths.root_key.read_bytes(), password=None)
        intermediate_key = serialization.load_pem_private_key(paths.intermediate_key.read_bytes(), password=None)
        root_cert = x509.load_pem_x509_certificate(paths.root_cert.read_bytes())
        online_root_cert = x509.load_pem_x509_certificate(paths.online_root_cert.read_bytes())
        intermediate_cert = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())

        if not isinstance(root_key, rsa.RSAPrivateKey) or root_key.key_size != 4096:
            raise CAInitializationError("Root CA private key profile is invalid")
        if not isinstance(intermediate_key, rsa.RSAPrivateKey) or intermediate_key.key_size != 3072:
            raise CAInitializationError("Intermediate CA private key profile is invalid")
        if _public_bytes(root_key.public_key()) != _public_bytes(root_cert.public_key()):
            raise CAInitializationError("Root certificate does not match root private key")
        if _public_bytes(intermediate_key.public_key()) != _public_bytes(intermediate_cert.public_key()):
            raise CAInitializationError("Intermediate certificate does not match intermediate private key")
        if root_cert.fingerprint(hashes.SHA256()) != online_root_cert.fingerprint(hashes.SHA256()):
            raise CAInitializationError("Online root certificate copy differs from root certificate")
        if root_cert.subject != root_cert.issuer:
            raise CAInitializationError("Root CA is not self-issued")
        if intermediate_cert.issuer != root_cert.subject:
            raise CAInitializationError("Intermediate CA issuer is invalid")

        root_constraints = root_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        intermediate_constraints = intermediate_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        if not root_constraints.ca or not intermediate_constraints.ca or intermediate_constraints.path_length != 0:
            raise CAInitializationError("CA basic constraints are invalid")

        _verify_rsa_signature(root_cert, root_cert)
        _verify_rsa_signature(root_cert, intermediate_cert)
    except CAInitializationError:
        raise
    except Exception as exc:
        raise CAInitializationError("Existing CA material is invalid") from exc


def initialize_ca(root_dir: Path, online_dir: Path) -> CAPaths:
    root_dir = Path(root_dir)
    online_dir = Path(online_dir)
    root_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    online_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root_dir, 0o700)
    os.chmod(online_dir, 0o700)

    paths = _paths(root_dir, online_dir)
    material = [
        paths.root_key,
        paths.root_cert,
        paths.online_root_cert,
        paths.intermediate_key,
        paths.intermediate_cert,
    ]
    existing = [path.exists() for path in material]

    if all(existing):
        _validate_existing(paths)
        return paths
    if any(existing):
        raise CAInitializationError("Partial CA material exists; refusing to overwrite or regenerate it")
    if (online_dir / "root-ca-key.pem").exists():
        raise CAInitializationError("Root CA private key must never exist in the online signer directory")

    now = datetime.now(UTC)
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    root_cert = _build_root(root_key, now)
    intermediate_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    intermediate_cert = _build_intermediate(intermediate_key, root_key, root_cert, now)

    root_cert_pem = root_cert.public_bytes(serialization.Encoding.PEM)
    _atomic_write(paths.root_key, _private_key_pem(root_key), 0o600)
    _atomic_write(paths.root_cert, root_cert_pem, 0o644)
    _atomic_write(paths.online_root_cert, root_cert_pem, 0o644)
    _atomic_write(paths.intermediate_key, _private_key_pem(intermediate_key), 0o600)
    _atomic_write(paths.intermediate_cert, intermediate_cert.public_bytes(serialization.Encoding.PEM), 0o644)

    _validate_existing(paths)
    return paths
