from datetime import datetime
from uuid import UUID
from fastapi import Depends,FastAPI,Header,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session,sessionmaker
from .config import Settings
from .models import Base,SoftwareSnapshot
settings=Settings()
engine=create_engine(settings.database_url,connect_args={"check_same_thread":False} if settings.database_url.startswith("sqlite") else {},pool_pre_ping=not settings.database_url.startswith("sqlite"))
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
if settings.database_url.startswith("sqlite"): Base.metadata.create_all(engine)
app=FastAPI(title="IT Guardian Software Inventory",version="0.9.0-dev.1")
class Package(BaseModel):
    name:str=Field(min_length=1,max_length=256);version:str=Field(default="",max_length=128);publisher:str=Field(default="",max_length=256);architecture:str=Field(default="",max_length=32)
class Snapshot(BaseModel):
    snapshot_id:UUID;collected_at:datetime;packages:list[Package]=Field(max_length=10000)
def db():
    s=SessionLocal()
    try: yield s
    finally:s.close()
def device_identity(x_guardian_proxy_token:str=Header(default=""),x_guardian_tenant_id:UUID=Header(),x_guardian_asset_id:UUID=Header(),x_guardian_device_id:UUID=Header()):
    if not settings.trusted_proxy_token or x_guardian_proxy_token!=settings.trusted_proxy_token: raise HTTPException(401,"trusted device proxy required")
    return x_guardian_tenant_id,x_guardian_asset_id,x_guardian_device_id
@app.get("/health/live")
def live():return {"status":"ok"}
@app.get("/health/ready")
def ready():
    with engine.connect() as c:c.execute(text("SELECT 1"))
    return {"status":"ready"}
@app.post("/api/v1/device/software/snapshots")
def ingest(payload:Snapshot,ident=Depends(device_identity),s:Session=Depends(db)):
    tenant,asset,device=ident
    existing=s.scalar(select(SoftwareSnapshot).where(SoftwareSnapshot.device_id==device,SoftwareSnapshot.snapshot_id==payload.snapshot_id))
    data=[p.model_dump() for p in payload.packages]
    if existing:
        if existing.packages!=data: raise HTTPException(409,"snapshot_id already used with different content")
        return {"snapshot_id":str(existing.snapshot_id),"duplicate":True,"packages":len(existing.packages)}
    row=SoftwareSnapshot(tenant_id=tenant,guardian_asset_id=asset,device_id=device,snapshot_id=payload.snapshot_id,collected_at=payload.collected_at,packages=data);s.add(row);s.commit()
    return {"snapshot_id":str(row.snapshot_id),"duplicate":False,"packages":len(data)}
@app.get("/api/v1/software")
def list_software(tenant_id:UUID=Query(),device_id:UUID|None=None,s:Session=Depends(db)):
    q=select(SoftwareSnapshot).where(SoftwareSnapshot.tenant_id==tenant_id)
    if device_id:q=q.where(SoftwareSnapshot.device_id==device_id)
    rows=s.scalars(q.order_by(SoftwareSnapshot.collected_at.desc())).all()
    latest={}
    for r in rows: latest.setdefault(r.device_id,r)
    return {"items":[{"device_id":str(r.device_id),"guardian_asset_id":str(r.guardian_asset_id),"snapshot_id":str(r.snapshot_id),"collected_at":r.collected_at.isoformat(),"packages":r.packages} for r in latest.values()]}
