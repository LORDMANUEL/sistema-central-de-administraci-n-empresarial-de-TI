from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from app.main import create_app


def test_tenant_api_requires_bearer_token(tmp_path, identity_crypto):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'auth-required.db'}", jwks=jwks)

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "tenant.authentication_required"


def test_tenant_api_rejects_refresh_token(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'refresh-rejected.db'}", jwks=jwks)

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants", headers=auth_header(token_type="refresh"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "tenant.invalid_token_type"


def test_tenant_api_rejects_token_signed_by_unknown_key(tmp_path, identity_crypto):
    jwks, make_token = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'bad-signature.db'}", jwks=jwks)
    other_key = Ed25519PrivateKey.generate()
    bad_token = make_token(key=other_key)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants",
            headers={"Authorization": f"Bearer {bad_token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "tenant.invalid_token"
