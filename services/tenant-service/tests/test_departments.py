from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def make_tenant(client, headers, slug):
    response = client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"name": slug.upper(), "slug": slug, "timezone": "UTC", "locale": "es-HN"},
    )
    assert response.status_code == 201
    return response.json()


def test_org_admin_can_build_department_hierarchy_and_viewer_can_read(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'departments.db'}", jwks=jwks)
    platform = auth_header()
    org_id, viewer_id = str(uuid4()), str(uuid4())

    with TestClient(app) as client:
        tenant = make_tenant(client, platform, "acme")
        for user_id, role in ((org_id, "org_admin"), (viewer_id, "viewer")):
            client.post(
                f"/api/v1/tenants/{tenant['id']}/memberships",
                headers=platform,
                json={"user_id": user_id, "role": role},
            )
        org = auth_header(role="org_admin", user_id=org_id)
        viewer = auth_header(role="viewer", user_id=viewer_id)
        parent = client.post(
            f"/api/v1/tenants/{tenant['id']}/departments",
            headers=org,
            json={"code": "IT", "name": "Information Technology"},
        )
        child = client.post(
            f"/api/v1/tenants/{tenant['id']}/departments",
            headers=org,
            json={"code": "SEC", "name": "Security", "parent_id": parent.json()["id"]},
        )
        listing = client.get(f"/api/v1/tenants/{tenant['id']}/departments", headers=viewer)

    assert parent.status_code == 201
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent.json()["id"]
    assert len(listing.json()) == 2


def test_department_parent_must_belong_to_same_tenant(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'department-cross-tenant.db'}", jwks=jwks)
    platform = auth_header()

    with TestClient(app) as client:
        first = make_tenant(client, platform, "first")
        second = make_tenant(client, platform, "second")
        foreign_parent = client.post(
            f"/api/v1/tenants/{first['id']}/departments",
            headers=platform,
            json={"code": "ROOT", "name": "Root"},
        ).json()
        response = client.post(
            f"/api/v1/tenants/{second['id']}/departments",
            headers=platform,
            json={"code": "BAD", "name": "Bad", "parent_id": foreign_parent["id"]},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tenant.department_parent_invalid"


def test_department_update_rejects_hierarchy_cycle(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'department-cycle.db'}", jwks=jwks)
    platform = auth_header()

    with TestClient(app) as client:
        tenant = make_tenant(client, platform, "cycle")
        parent = client.post(
            f"/api/v1/tenants/{tenant['id']}/departments",
            headers=platform,
            json={"code": "A", "name": "A"},
        ).json()
        child = client.post(
            f"/api/v1/tenants/{tenant['id']}/departments",
            headers=platform,
            json={"code": "B", "name": "B", "parent_id": parent["id"]},
        ).json()
        response = client.patch(
            f"/api/v1/tenants/{tenant['id']}/departments/{parent['id']}",
            headers=platform,
            json={"parent_id": child["id"]},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tenant.department_cycle"


def test_department_code_unique_per_tenant(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'department-unique.db'}", jwks=jwks)
    platform = auth_header()

    with TestClient(app) as client:
        tenant = make_tenant(client, platform, "unique")
        first = client.post(
            f"/api/v1/tenants/{tenant['id']}/departments",
            headers=platform,
            json={"code": "IT", "name": "IT"},
        )
        second = client.post(
            f"/api/v1/tenants/{tenant['id']}/departments",
            headers=platform,
            json={"code": "IT", "name": "Duplicate"},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "tenant.department_code_already_exists"
