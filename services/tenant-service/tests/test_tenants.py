from fastapi.testclient import TestClient

from app.main import create_app


def tenant_payload(slug="acme"):
    return {
        "name": "ACME Honduras",
        "slug": slug,
        "timezone": "America/Tegucigalpa",
        "locale": "es-HN",
    }


def test_platform_admin_can_create_list_get_and_update_tenant(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant-crud.db'}", jwks=jwks)
    headers = auth_header(role="platform_admin")

    with TestClient(app) as client:
        created = client.post("/api/v1/tenants", headers=headers, json=tenant_payload())
        listing = client.get("/api/v1/tenants", headers=headers)
        detail = client.get(f"/api/v1/tenants/{created.json()['id']}", headers=headers)
        updated = client.patch(
            f"/api/v1/tenants/{created.json()['id']}",
            headers=headers,
            json={"name": "ACME Central", "status": "suspended"},
        )

    assert created.status_code == 201
    assert created.json()["slug"] == "acme"
    assert created.json()["status"] == "active"
    assert len(listing.json()) == 1
    assert detail.json()["id"] == created.json()["id"]
    assert updated.status_code == 200
    assert updated.json()["name"] == "ACME Central"
    assert updated.json()["status"] == "suspended"


def test_non_platform_admin_cannot_create_tenant(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant-create-forbidden.db'}", jwks=jwks)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants",
            headers=auth_header(role="viewer"),
            json=tenant_payload(),
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant.platform_admin_required"


def test_duplicate_tenant_slug_returns_conflict(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant-duplicate.db'}", jwks=jwks)
    headers = auth_header()

    with TestClient(app) as client:
        first = client.post("/api/v1/tenants", headers=headers, json=tenant_payload())
        second = client.post("/api/v1/tenants", headers=headers, json=tenant_payload())

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "tenant.slug_already_exists"


def test_invalid_timezone_is_rejected(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant-timezone.db'}", jwks=jwks)
    payload = tenant_payload()
    payload["timezone"] = "Mars/Olympus"

    with TestClient(app) as client:
        response = client.post("/api/v1/tenants", headers=auth_header(), json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "tenant.validation_error"
