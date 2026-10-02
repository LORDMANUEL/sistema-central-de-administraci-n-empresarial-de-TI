from datetime import UTC,datetime
from uuid import uuid4
import os
os.environ["SOFTWARE_DATABASE_URL"]="sqlite+pysqlite:///:memory:"
os.environ["SOFTWARE_TRUSTED_PROXY_TOKEN"]="test-secret"
from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
def test_health_and_snapshot_idempotency():
    assert c.get("/health/ready").status_code==200
    tenant,asset,device,snap=[uuid4() for _ in range(4)]
    h={"X-Guardian-Proxy-Token":"test-secret","X-Guardian-Tenant-ID":str(tenant),"X-Guardian-Asset-ID":str(asset),"X-Guardian-Device-ID":str(device)}
    body={"snapshot_id":str(snap),"collected_at":datetime.now(UTC).isoformat(),"packages":[{"name":"Example","version":"1.0","publisher":"Vendor","architecture":"x64"}]}
    assert c.post("/api/v1/device/software/snapshots",headers=h,json=body).json()["duplicate"] is False
    assert c.post("/api/v1/device/software/snapshots",headers=h,json=body).json()["duplicate"] is True
    items=c.get("/api/v1/software",params={"tenant_id":str(tenant)}).json()["items"]
    assert items[0]["packages"][0]["name"]=="Example"
def test_rejects_untrusted_device():
    u=uuid4();r=c.post("/api/v1/device/software/snapshots",headers={"X-Guardian-Tenant-ID":str(u),"X-Guardian-Asset-ID":str(u),"X-Guardian-Device-ID":str(u)},json={"snapshot_id":str(u),"collected_at":datetime.now(UTC).isoformat(),"packages":[]})
    assert r.status_code==401
