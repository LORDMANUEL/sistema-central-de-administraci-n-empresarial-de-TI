from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from .ca import initialize_ca


def main() -> None:
    root_dir = Path(os.environ.get("PKI_CA_ROOT_DIR", "/var/lib/guardian/pki-root"))
    online_dir = Path(os.environ.get("PKI_CA_ONLINE_DIR", "/var/lib/guardian/pki"))
    paths = initialize_ca(root_dir, online_dir)
    root_cert = x509.load_pem_x509_certificate(paths.root_cert.read_bytes())
    intermediate_cert = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())
    print(
        json.dumps(
            {
                "status": "ok",
                "root_fingerprint_sha256": root_cert.fingerprint(hashes.SHA256()).hex(),
                "intermediate_fingerprint_sha256": intermediate_cert.fingerprint(hashes.SHA256()).hex(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
