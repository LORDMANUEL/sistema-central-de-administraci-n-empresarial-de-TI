from uuid import uuid4
from fastapi import FastAPI,Request,Response
from sqlalchemy import text
from .api import router
from .auth import AccessTokenVerifier
from .config import Settings,get_settings
from .database import Base,build_engine,build_session_factory
from .errors import GuardianError,guardian_error_handler
from .metrics import HTTP_REQUESTS,render_metrics
from .upstream import CoreValidator
def create_app(*,database_url:str|None=None):
 s=get_settings() if database_url is None else Settings(database_url=database_url,trusted_proxy_token="test-proxy");engine=build_engine(s.database_url)
 if s.database_url.startswith("sqlite"):Base.metadata.create_all(engine)
 app=FastAPI(title="IT Guardian Telemetry Service",version="0.6.0-dev.1");app.state.settings=s;app.state.engine=engine;app.state.session_factory=build_session_factory(engine);app.state.auth=AccessTokenVerifier(s);app.state.core_validator=CoreValidator(s);app.state.device_principal_resolver=None;app.add_exception_handler(GuardianError,guardian_error_handler);app.include_router(router)
 @app.middleware("http")
 async def ctx(request:Request,call_next):request.state.request_id=request.headers.get("X-Request-ID") or str(uuid4());response=await call_next(request);response.headers["X-Request-ID"]=request.state.request_id;HTTP_REQUESTS.labels(request.method,request.url.path,str(response.status_code)).inc();return response
 @app.get("/health/live")
 def live():return {"status":"ok"}
 @app.get("/health/ready")
 def ready():
  try:
   with engine.connect() as c:c.execute(text("SELECT 1"))
  except Exception as exc:raise GuardianError(503,"telemetry.database_unavailable","Telemetry database unavailable") from exc
  return {"status":"ready"}
 @app.get("/metrics")
 def metrics():p,ct=render_metrics();return Response(content=p,media_type=ct)
 return app
app=create_app()
