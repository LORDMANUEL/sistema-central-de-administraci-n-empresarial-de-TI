from fastapi.testclient import TestClient

from app.auth import IdentityPrincipal
from app.errors import GuardianError
from app.main import create_app
from app.tenant_access import TenantAccessDecision

TENANT_ID = "11111111-1111-1111-1111-111111111111"
SITE_ID = "22222222-2222-2222-2222-222222222222"
DEPARTMENT_ID = "33333333-3333-3333-3333-333333333333"


def _resolver(role: str, *, status: str = "active", allowed: bool = True):
    def resolve(tenant_id: str, user_id: str) -> TenantAccessDecision:
        assert tenant_id == TENANT_ID
        return TenantAccessDecision(allowed=allowed, role=role, tenant_status=status)

    return resolve


def _valid_references(tenant_id: str, site_id: str | None, department_id: str | None) -> None:
    assert tenant_id == TENANT_ID
    if site_id not in (None, SITE_ID):
        raise GuardianError(422, "asset.site_reference_invalid", "Site does not belong to tenant")
    if department_id not in (None, DEPARTMENT_ID):
        raise GuardianError(422, "asset.department_reference_invalid", "Department does not belong to tenant")


def _client(tmp_path, *, principal: IdentityPrincipal, role: str, tenant_status: str = "active"):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'asset.db'}", auth_disabled=True)
    app.state.auth_disabled_principal = principal
    app.state.tenant_access_resolver = _resolver(role, status=tenant_status)
    app.state.tenant_reference_validator = _valid_references
    return app, TestClient(app)


def test_org_admin_can_create_asset_and_member_can_read_it(tmp_path):
    app, client = _client(
        tmp_path,
        principal=IdentityPrincipal(user_id="org-user", role="viewer"),
        role="org_admin",
    )
    with client:
        created = client.post(
            "/api/v1/assets",
            json={
                "tenant_id": TENANT_ID,
                "site_id": SITE_ID,
                "department_id": DEPARTMENT_ID,
                "asset_type": "computer",
                "display_name": "WS-SPS-001",
            },
        )
        assert created.status_code == 201, created.text
        asset_id = created.json()["guardian_asset_id"]

        app.state.auth_disabled_principal = IdentityPrincipal(user_id="member-user", role="viewer")
        app.state.tenant_access_resolver = _resolver("viewer")

        listed = client.get("/api/v1/assets", params={"tenant_id": TENANT_ID})
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["guardian_asset_id"] == asset_id

        fetched = client.get(f"/api/v1/assets/{asset_id}")
        assert fetched.status_code == 200, fetched.text


def test_read_only_member_cannot_create_or_link_external_identity(tmp_path):
    app, client = _client(
        tmp_path,
        principal=IdentityPrincipal(user_id="member-user", role="viewer"),
        role="viewer",
    )
    with client:
        denied = client.post(
            "/api/v1/assets",
            json={"tenant_id": TENANT_ID, "asset_type": "computer", "display_name": "WS-001"},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "asset.org_admin_required"


def test_suspended_tenant_is_blocked(tmp_path):
    _, client = _client(
        tmp_path,
        principal=IdentityPrincipal(user_id="member-user", role="viewer"),
        role="org_admin",
        tenant_status="suspended",
    )
    with client:
        denied = client.get("/api/v1/assets", params={"tenant_id": TENANT_ID})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "asset.tenant_suspended"


def test_invalid_site_or_department_is_rejected_before_asset_persist(tmp_path):
    app, client = _client(
        tmp_path,
        principal=IdentityPrincipal(user_id="org-user", role="viewer"),
        role="org_admin",
    )
    with client:
        response = client.post(
            "/api/v1/assets",
            json={
                "tenant_id": TENANT_ID,
                "site_id": "99999999-9999-9999-9999-999999999999",
                "asset_type": "computer",
                "display_name": "WS-INVALID",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "asset.site_reference_invalid"

        with app.state.session_factory() as session:
            from app.models import Asset

            assert session.query(Asset).count() == 0
