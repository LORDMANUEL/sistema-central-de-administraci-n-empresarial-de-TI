import jwt
from fastapi.testclient import TestClient

from app.main import create_app


ADMIN = {
    "email": "admin@example.com",
    "display_name": "Platform Admin",
    "password": "Correct-Horse-Battery-Staple-2026!",
}


def test_jwks_exposes_public_ed25519_key_that_verifies_access_tokens(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'jwks.db'}")

    with TestClient(app) as client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        )
        jwks = client.get("/.well-known/jwks.json")

    assert login.status_code == 200
    assert jwks.status_code == 200
    keys = jwks.json()["keys"]
    assert len(keys) == 1
    public_jwk = keys[0]
    assert public_jwk["kty"] == "OKP"
    assert public_jwk["crv"] == "Ed25519"
    assert public_jwk["use"] == "sig"
    assert public_jwk["alg"] == "EdDSA"
    assert public_jwk["kid"] == app.state.settings.jwt_key_id
    assert "x" in public_jwk
    assert "d" not in public_jwk

    access_token = login.json()["access_token"]
    header = jwt.get_unverified_header(access_token)
    assert header["alg"] == "EdDSA"
    assert header["kid"] == app.state.settings.jwt_key_id

    decoded = jwt.decode(
        access_token,
        jwt.PyJWK.from_dict(public_jwk).key,
        algorithms=["EdDSA"],
        issuer=app.state.settings.jwt_issuer,
        audience=app.state.settings.jwt_audience,
    )
    assert decoded["type"] == "access"
    assert decoded["role"] == "platform_admin"


def test_tokens_include_issuer_and_audience_claims(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'claims.db'}")

    with TestClient(app) as client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        access_token = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        ).json()["access_token"]
        public_jwk = client.get("/.well-known/jwks.json").json()["keys"][0]

    claims = jwt.decode(
        access_token,
        jwt.PyJWK.from_dict(public_jwk).key,
        algorithms=["EdDSA"],
        issuer=app.state.settings.jwt_issuer,
        audience=app.state.settings.jwt_audience,
    )
    assert claims["iss"] == app.state.settings.jwt_issuer
    assert claims["aud"] == app.state.settings.jwt_audience
