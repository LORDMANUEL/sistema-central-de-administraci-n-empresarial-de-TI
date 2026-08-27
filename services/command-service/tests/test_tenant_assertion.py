from uuid import uuid4
from app.schemas import CommandCreate

def test_command_accepts_tenant_audit_assertion():
    tenant_id = uuid4()
    payload = CommandCreate(tenant_id=tenant_id, device_id=uuid4(), guardian_asset_id=uuid4(), command_type="inventory.refresh", arguments={}, idempotency_key="x", expires_in_seconds=30)
    assert payload.tenant_id == tenant_id
