import stat

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.ca import initialize_ca


def _verify_rsa_signature(issuer_cert: x509.Certificate, subject_cert: x509.Certificate) -> None:
    issuer_cert.public_key().verify(
        subject_cert.signature,
        subject_cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        subject_cert.signature_hash_algorithm,
    )


def test_initialize_ca_creates_root_and_online_intermediate(tmp_path):
    root_dir = tmp_path / "root"
    online_dir = tmp_path / "online"

    paths = initialize_ca(root_dir, online_dir)

    root_cert = x509.load_pem_x509_certificate(paths.root_cert.read_bytes())
    root_key = serialization.load_pem_private_key(paths.root_key.read_bytes(), password=None)
    intermediate_cert = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())
    intermediate_key = serialization.load_pem_private_key(paths.intermediate_key.read_bytes(), password=None)

    assert isinstance(root_key, rsa.RSAPrivateKey)
    assert root_key.key_size == 4096
    assert isinstance(intermediate_key, rsa.RSAPrivateKey)
    assert intermediate_key.key_size == 3072

    root_bc = root_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    intermediate_bc = intermediate_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert root_bc.ca is True
    assert intermediate_bc.ca is True
    assert intermediate_bc.path_length == 0

    _verify_rsa_signature(root_cert, root_cert)
    _verify_rsa_signature(root_cert, intermediate_cert)

    assert paths.root_key.parent == root_dir
    assert not (online_dir / "root-ca-key.pem").exists()
    assert (online_dir / "root-ca-cert.pem").read_bytes() == paths.root_cert.read_bytes()
    assert stat.S_IMODE(paths.root_key.stat().st_mode) == 0o600
    assert stat.S_IMODE(paths.intermediate_key.stat().st_mode) == 0o600


def test_initialize_ca_is_idempotent_and_does_not_rotate_existing_ca(tmp_path):
    root_dir = tmp_path / "root"
    online_dir = tmp_path / "online"

    first = initialize_ca(root_dir, online_dir)
    first_bytes = {
        "root_key": first.root_key.read_bytes(),
        "root_cert": first.root_cert.read_bytes(),
        "intermediate_key": first.intermediate_key.read_bytes(),
        "intermediate_cert": first.intermediate_cert.read_bytes(),
    }

    second = initialize_ca(root_dir, online_dir)

    assert second.root_key.read_bytes() == first_bytes["root_key"]
    assert second.root_cert.read_bytes() == first_bytes["root_cert"]
    assert second.intermediate_key.read_bytes() == first_bytes["intermediate_key"]
    assert second.intermediate_cert.read_bytes() == first_bytes["intermediate_cert"]

    root_cert = x509.load_pem_x509_certificate(second.root_cert.read_bytes())
    assert root_cert.fingerprint(hashes.SHA256()) == x509.load_pem_x509_certificate(first_bytes["root_cert"]).fingerprint(hashes.SHA256())
