from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def setup_tenant_with_members(client, auth_header):
    platform = auth_header()
    tenant = client.post(
        "/api/v1/tenants",
        headers=platform,
        json={"name": "YUDE", "slug": "yude", "timezone": "America/Tegucigalpa", "locale": "es-HN"},
    ).json()
    org_id = str(uuid4())
    viewer_id = str(uuid4())
    for user_id, role in ((org_id, "org_admin"), (viewer_id, "viewer")):
        assert client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=platform,
            json={"user_id": user_id, "role": role},
        ).status_code == 201
    return tenant, auth_header(role="org_admin", user_id=org_id), auth_header(role="viewer", user_id=viewer_id)


def site_payload(code="SPS"):
    return {
        "code": code,
        "name": "San Pedro Sula",
        "timezone": "America/Tegucigalpa",
        "country_code": "HN",
        "region": "Cortes",
        "city": "San Pedro Sula",
        "address_line1": "Boulevard principal",
        "latitude": 15.5057,
        "longitude": -88.0250,
    }


def test_org_admin_can_create_update_and_viewer_can_list_sites(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'sites.db'}", jwks=jwks)

    with TestClient(app) as client:
        tenant, org_headers, viewer_headers = setup_tenant_with_members(client, auth_header)
        created = client.post(f"/api/v1/tenants/{tenant['id']}/sites", headers=org_headers, json=site_payload())
        listing = client.get(f"/api/v1/tenants/{tenant['id']}/sites", headers=viewer_headers)
        updated = client.patch(
            f"/api/v1/tenants/{tenant['id']}/sites/{created.json()['id']}",
            headers=org_headers,
            json={"name": "SPS Principal", "status": "inactive"},
        )

    assert created.status_code == 201
    assert created.json()["code"] == "SPS"
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [created.json()["id"]]
    assert updated.status_code == 200
    assert updated.json()["name"] == "SPS Principal"
    assert updated.json()["status"] == "inactive"


def test_viewer_cannot_create_site(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'site-forbidden.db'}", jwks=jwks)

    with TestClient(app) as client:
        tenant, _, viewer_headers = setup_tenant_with_members(client, auth_header)
        response = client.post(f"/api/v1/tenants/{tenant['id']}/sites", headers=viewer_headers, json=site_payload())

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant.org_admin_required"


def test_site_code_is_unique_within_tenant_but_reusable_between_tenants(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'site-unique.db'}", jwks=jwks)
    platform = auth_header()

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/tenants",
            headers=platform,
            json={"name": "One", "slug": "one", "timezone": "UTC", "locale": "es-HN"},
        ).json()
        second = client.post(
            "/api/v1/tenants",
            headers=platform,
            json={"name": "Two", "slug": "two", "timezone": "UTC", "locale": "es-HN"},
        ).json()
        first_create = client.post(f"/api/v1/tenants/{first['id']}/sites", headers=platform, json=site_payload("HQ"))
        duplicate = client.post(f"/api/v1/tenants/{first['id']}/sites", headers=platform, json=site_payload("HQ"))
        other_tenant = client.post(f"/api/v1/tenants/{second['id']}/sites", headers=platform, json=site_payload("HQ"))

    assert first_create.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "tenant.site_code_already_exists"
    assert other_tenant.status_code == 201
