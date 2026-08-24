from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.asset_client import AssetReference
from app.auth import IdentityAccessVerifier, TenantAccessDecision
from app.database import Base
from app.main import create_app
from app.models import EnrollmentToken, OutboxEvent


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


class FakeAssetClient:
    def __init__(self, *, tenant_id: str = "tenant-1") -> None:
        self.tenant_id = tenant_id
        self.calls = []

    def get(self, asset_id: str, bearer_token: str) -> AssetReference:
        self.calls.append((asset_id, bearer_token))
        return AssetReference(
            asset_id=asset_id,
            tenant_id=self.tenant_id,
            status="active",
            asset_type="computer",
            display_name="WS-001",
        )


def _app(tmp_path, identity_jwks):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'token-api.db'}",
        signing_key=_seed(),
    )
    Base.metadata.create_all(app.state.engine)
    app.state.identity_verifier = IdentityAccessVerifier(app.state.settings, jwks=identity_jwks)
    app.state.tenant_access_resolver = lambda tenant_id, user_id, token: TenantAccessDecision(
        allowed=True,
        role="org_admin",
        tenant_status="active",
    )
    app.state.asset_client = FakeAssetClient()
    return app


def test_create_token_validates_asset_returns_plaintext_once_and_persists_only_hash(
    tmp_path, identity_crypto, make_identity_token
):
    _, _, jwks = identity_crypto
    app = _app(tmp_path, jwks)
    admin_token = make_identity_token(role="viewer", user_id="org-admin-1")

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/enrollment-tokens",
            json={"tenant_id": "tenant-1", "asset_id": "asset-1", "expires_in_minutes": 60},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        listed = client.get(
            "/api/v1/enrollment-tokens",
            params={"tenant_id": "tenant-1"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert created.status_code == 201, created.text
    body = created.json()
    plaintext = body["token"]
    assert plaintext.startswith("gdt_")
    assert body["tenant_id"] == "tenant-1"
    assert body["asset_id"] == "asset-1"
    assert body["token_hint"]
    assert "token_hash" not in body

    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    listed_item = listed.json()[0]
    assert listed_item["id"] == body["id"]
    assert "token" not in listed_item
    assert "token_hash" not in listed_item
    assert plaintext not in listed.text

    assert app.state.asset_client.calls == [("asset-1", admin_token)]
    with app.state.session_factory() as session:
        token = session.query(EnrollmentToken).one()
        assert token.token_hash != plaintext
        assert plaintext not in token.token_hint
        event = session.query(OutboxEvent).one()
        assert event.event_type == "enrollment.token.created"
        serialized = str(event.payload)
        assert plaintext not in serialized
        assert token.token_hash not in serialized


def test_create_token_rejects_cross_tenant_asset_without_persisting(tmp_path, identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    app = _app(tmp_path, jwks)
    app.state.asset_client = FakeAssetClient(tenant_id="tenant-2")
    admin_token = make_identity_token(role="platform_admin")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/enrollment-tokens",
            json={"tenant_id": "tenant-1", "asset_id": "asset-1", "expires_in_minutes": 60},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "enrollment.asset_tenant_mismatch"
    with app.state.session_factory() as session:
        assert session.query(EnrollmentToken).count() == 0
        assert session.query(OutboxEvent).count() == 0


def test_token_ttl_range_is_enforced(tmp_path, identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    app = _app(tmp_path, jwks)
    headers = {"Authorization": f"Bearer {make_identity_token(role='platform_admin')}"}

    with TestClient(app) as client:
        too_short = client.post(
            "/api/v1/enrollment-tokens",
            json={"tenant_id": "tenant-1", "asset_id": "asset-1", "expires_in_minutes": 4},
            headers=headers,
        )
        too_long = client.post(
            "/api/v1/enrollment-tokens",
            json={"tenant_id": "tenant-1", "asset_id": "asset-1", "expires_in_minutes": 1441},
            headers=headers,
        )

    assert too_short.status_code == 422
    assert too_long.status_code == 422


def test_revoke_token_is_idempotent_and_emits_one_event(tmp_path, identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    app = _app(tmp_path, jwks)
    headers = {"Authorization": f"Bearer {make_identity_token(role='platform_admin')}"}

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/enrollment-tokens",
            json={"tenant_id": "tenant-1", "asset_id": "asset-1", "expires_in_minutes": 60},
            headers=headers,
        )
        token_id = created.json()["id"]
        first = client.post(f"/api/v1/enrollment-tokens/{token_id}/revoke", headers=headers)
        second = client.post(f"/api/v1/enrollment-tokens/{token_id}/revoke", headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["status"] == "revoked"
    assert second.json()["revoked_at"] == first.json()["revoked_at"]
    with app.state.session_factory() as session:
        events = session.query(OutboxEvent).all()
        assert [event.event_type for event in events].count("enrollment.token.created") == 1
        assert [event.event_type for event in events].count("enrollment.token.revoked") == 1
