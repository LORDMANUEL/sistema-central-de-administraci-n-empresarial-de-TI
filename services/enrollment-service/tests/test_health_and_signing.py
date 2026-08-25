import base64

from fastapi.testclient import TestClient

from app.main import create_app


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


def test_live_is_ok_even_if_signer_configuration_is_missing(tmp_path):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'enrollment.db'}",
        signing_key="",
    )
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "enrollment-service"}


def test_ready_is_503_when_signing_seed_is_missing_or_invalid(tmp_path):
    missing = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'missing.db'}",
        signing_key="",
    )
    invalid = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'invalid.db'}",
        signing_key="not-a-valid-seed",
    )

    for app in (missing, invalid):
        with TestClient(app) as client:
            response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "enrollment.signer_unavailable"
        assert response.headers["X-Request-ID"]


def test_valid_signer_makes_service_ready_and_exposes_public_jwks_only(tmp_path):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'valid.db'}",
        signing_key=_seed(),
    )

    with TestClient(app) as client:
        ready = client.get("/health/ready")
        jwks = client.get("/.well-known/jwks.json")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "service": "enrollment-service"}
    assert jwks.status_code == 200
    body = jwks.json()
    assert len(body["keys"]) == 1
    key = body["keys"][0]
    assert key["kty"] == "OKP"
    assert key["crv"] == "Ed25519"
    assert key["alg"] == "EdDSA"
    assert key["kid"] == "enrollment-ed25519-v1"
    assert "d" not in key
    assert _seed() not in jwks.text
