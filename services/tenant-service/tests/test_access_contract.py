from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def _create_tenant(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/tenants",
        json={
            "name": "Acme Honduras",
            "slug": f"acme-{str(uuid4())[:8]}",
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_access_contract_returns_membership_role_and_suspended_state(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant.db'}", jwks=jwks)
    admin_headers = auth_header(role="platform_admin")
    user_id = str(uuid4())
    user_headers = auth_header(role="viewer", user_id=user_id)

    with TestClient(app) as client:
        tenant_id = _create_tenant(client, admin_headers)
        membership = client.post(
            f"/api/v1/tenants/{tenant_id}/memberships",
            json={"user_id": user_id, "role": "org_admin"},
            headers=admin_headers,
        )
        assert membership.status_code == 201, membership.text

        access = client.get(f"/api/v1/tenants/{tenant_id}/access", headers=user_headers)
        assert access.status_code == 200, access.text
        assert access.json() == {
            "allowed": True,
            "role": "org_admin",
            "tenant_status": "active",
        }

        suspended = client.patch(
            f"/api/v1/tenants/{tenant_id}",
            json={"status": "suspended"},
            headers=admin_headers,
        )
        assert suspended.status_code == 200, suspended.text

        access = client.get(f"/api/v1/tenants/{tenant_id}/access", headers=user_headers)
        assert access.status_code == 200, access.text
        assert access.json()["allowed"] is True
        assert access.json()["tenant_status"] == "suspended"


def test_access_contract_denies_non_member(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant.db'}", jwks=jwks)
    admin_headers = auth_header(role="platform_admin")
    outsider_headers = auth_header(role="viewer", user_id=str(uuid4()))

    with TestClient(app) as client:
        tenant_id = _create_tenant(client, admin_headers)
        response = client.get(f"/api/v1/tenants/{tenant_id}/access", headers=outsider_headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "tenant.access_denied"


def test_reference_validation_requires_site_and_department_from_same_tenant(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant.db'}", jwks=jwks)
    admin_headers = auth_header(role="platform_admin")

    with TestClient(app) as client:
        tenant_id = _create_tenant(client, admin_headers)
        site = client.post(
            f"/api/v1/tenants/{tenant_id}/sites",
            json={"code": "SPS", "name": "San Pedro Sula"},
            headers=admin_headers,
        )
        assert site.status_code == 201, site.text
        department = client.post(
            f"/api/v1/tenants/{tenant_id}/departments",
            json={"code": "IT", "name": "Tecnologia"},
            headers=admin_headers,
        )
        assert department.status_code == 201, department.text

        valid = client.post(
            f"/api/v1/tenants/{tenant_id}/references/validate",
            json={"site_id": site.json()["id"], "department_id": department.json()["id"]},
            headers=admin_headers,
        )
        assert valid.status_code == 200, valid.text
        assert valid.json()["valid"] is True

        invalid = client.post(
            f"/api/v1/tenants/{tenant_id}/references/validate",
            json={"site_id": str(uuid4()), "department_id": department.json()["id"]},
            headers=admin_headers,
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "tenant.site_reference_invalid"
