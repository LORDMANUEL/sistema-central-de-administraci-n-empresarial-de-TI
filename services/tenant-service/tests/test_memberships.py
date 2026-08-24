from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def create_tenant(client, headers, slug="acme"):
    response = client.post(
        "/api/v1/tenants",
        headers=headers,
        json={
            "name": f"Tenant {slug}",
            "slug": slug,
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_platform_admin_can_add_membership_and_member_sees_own_tenant(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'membership.db'}", jwks=jwks)
    admin_headers = auth_header()
    user_id = str(uuid4())

    with TestClient(app) as client:
        tenant = create_tenant(client, admin_headers)
        added = client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=admin_headers,
            json={"user_id": user_id, "role": "viewer"},
        )
        member_headers = auth_header(role="viewer", user_id=user_id)
        listing = client.get("/api/v1/tenants", headers=member_headers)
        detail = client.get(f"/api/v1/tenants/{tenant['id']}", headers=member_headers)

    assert added.status_code == 201
    assert added.json()["user_id"] == user_id
    assert added.json()["role"] == "viewer"
    assert added.json()["is_active"] is True
    assert [item["id"] for item in listing.json()] == [tenant["id"]]
    assert detail.status_code == 200


def test_org_admin_membership_can_manage_members_but_viewer_cannot(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'membership-role.db'}", jwks=jwks)
    platform_headers = auth_header()
    org_admin_id = str(uuid4())
    viewer_id = str(uuid4())

    with TestClient(app) as client:
        tenant = create_tenant(client, platform_headers)
        for user_id, role in ((org_admin_id, "org_admin"), (viewer_id, "viewer")):
            response = client.post(
                f"/api/v1/tenants/{tenant['id']}/memberships",
                headers=platform_headers,
                json={"user_id": user_id, "role": role},
            )
            assert response.status_code == 201

        org_headers = auth_header(role="org_admin", user_id=org_admin_id)
        viewer_headers = auth_header(role="viewer", user_id=viewer_id)
        new_user = str(uuid4())
        org_add = client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=org_headers,
            json={"user_id": new_user, "role": "helpdesk"},
        )
        viewer_add = client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=viewer_headers,
            json={"user_id": str(uuid4()), "role": "viewer"},
        )
        listing = client.get(f"/api/v1/tenants/{tenant['id']}/memberships", headers=org_headers)

    assert org_add.status_code == 201
    assert viewer_add.status_code == 403
    assert viewer_add.json()["error"]["code"] == "tenant.org_admin_required"
    assert len(listing.json()) == 3


def test_membership_upsert_updates_existing_user_without_duplicate_row(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'membership-upsert.db'}", jwks=jwks)
    headers = auth_header()
    user_id = str(uuid4())

    with TestClient(app) as client:
        tenant = create_tenant(client, headers)
        first = client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=headers,
            json={"user_id": user_id, "role": "viewer"},
        )
        second = client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=headers,
            json={"user_id": user_id, "role": "it_operator"},
        )
        listing = client.get(f"/api/v1/tenants/{tenant['id']}/memberships", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["role"] == "it_operator"
    assert len(listing.json()) == 1


def test_disabling_membership_removes_tenant_access(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'membership-disable.db'}", jwks=jwks)
    platform_headers = auth_header()
    user_id = str(uuid4())

    with TestClient(app) as client:
        tenant = create_tenant(client, platform_headers)
        client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=platform_headers,
            json={"user_id": user_id, "role": "viewer"},
        )
        disabled = client.patch(
            f"/api/v1/tenants/{tenant['id']}/memberships/{user_id}",
            headers=platform_headers,
            json={"is_active": False},
        )
        member_headers = auth_header(role="viewer", user_id=user_id)
        detail = client.get(f"/api/v1/tenants/{tenant['id']}", headers=member_headers)

    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert detail.status_code == 403
    assert detail.json()["error"]["code"] == "tenant.access_denied"


def test_suspended_tenant_denies_members_but_platform_admin_can_read(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'membership-suspended.db'}", jwks=jwks)
    platform_headers = auth_header()
    user_id = str(uuid4())

    with TestClient(app) as client:
        tenant = create_tenant(client, platform_headers)
        client.post(
            f"/api/v1/tenants/{tenant['id']}/memberships",
            headers=platform_headers,
            json={"user_id": user_id, "role": "viewer"},
        )
        client.patch(
            f"/api/v1/tenants/{tenant['id']}",
            headers=platform_headers,
            json={"status": "suspended"},
        )
        member_detail = client.get(
            f"/api/v1/tenants/{tenant['id']}",
            headers=auth_header(role="viewer", user_id=user_id),
        )
        platform_detail = client.get(f"/api/v1/tenants/{tenant['id']}", headers=platform_headers)

    assert member_detail.status_code == 403
    assert member_detail.json()["error"]["code"] == "tenant.suspended"
    assert platform_detail.status_code == 200
