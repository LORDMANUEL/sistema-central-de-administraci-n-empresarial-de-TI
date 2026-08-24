from fastapi.testclient import TestClient

from app.main import create_app


def test_create_and_list_asset_with_generated_guardian_id(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'asset.db'}", auth_disabled=True)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/assets",
            json={
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "site_id": "22222222-2222-2222-2222-222222222222",
                "asset_type": "computer",
                "display_name": "WS-SPS-001",
                "hostname": "ws-sps-001",
                "serial_number": "ABC123",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["guardian_asset_id"]
        assert body["tenant_id"] == "11111111-1111-1111-1111-111111111111"
        assert body["asset_type"] == "computer"
        assert body["status"] == "active"

        listed = client.get(
            "/api/v1/assets",
            params={"tenant_id": "11111111-1111-1111-1111-111111111111"},
        )
        assert listed.status_code == 200
        assert [item["guardian_asset_id"] for item in listed.json()] == [body["guardian_asset_id"]]


def test_asset_create_persists_outbox_event_in_same_database(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'asset.db'}", auth_disabled=True)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assets",
            json={
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "asset_type": "server",
                "display_name": "SRV-001",
            },
        )
        assert response.status_code == 201, response.text

    with app.state.session_factory() as session:
        from app.models import OutboxEvent

        events = session.query(OutboxEvent).all()
        assert len(events) == 1
        assert events[0].event_type == "asset.created"
        assert events[0].aggregate_id == response.json()["guardian_asset_id"]
        assert events[0].published_at is None


def test_external_identity_is_idempotent_and_unique(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'asset.db'}", auth_disabled=True)
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/assets",
            json={
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "asset_type": "computer",
                "display_name": "WS-001",
            },
        ).json()
        second = client.post(
            "/api/v1/assets",
            json={
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "asset_type": "computer",
                "display_name": "WS-002",
            },
        ).json()

        linked = client.post(
            f"/api/v1/assets/{first['guardian_asset_id']}/external-identities",
            json={"provider": "tactical-rmm", "external_id": "agent-123"},
        )
        assert linked.status_code == 201, linked.text

        repeated = client.post(
            f"/api/v1/assets/{first['guardian_asset_id']}/external-identities",
            json={"provider": "tactical-rmm", "external_id": "agent-123"},
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["guardian_asset_id"] == first["guardian_asset_id"]

        collision = client.post(
            f"/api/v1/assets/{second['guardian_asset_id']}/external-identities",
            json={"provider": "tactical-rmm", "external_id": "agent-123"},
        )
        assert collision.status_code == 409
        assert collision.json()["error"]["code"] == "asset.external_identity_conflict"
