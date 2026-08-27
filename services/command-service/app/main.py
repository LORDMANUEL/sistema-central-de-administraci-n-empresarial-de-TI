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
    settings=get_settings() if database_url is None else Settings(database_url=database_url,trusted_proxy_token="test-proxy")
    engine=build_engine(settings.database_url)
    if settings.database_url.startswith("sqlite"):Base.metadata.create_all(engine)
    app=FastAPI(title="IT Guardian Command Service",version="0.6.0-dev.1");app.state.settings=settings;app.state.engine=engine;app.state.session_factory=build_session_factory(engine);app.state.auth=AccessTokenVerifier(settings);app.state.core_validator=CoreValidator(settings);app.state.device_principal_resolver=None;app.add_exception_handler(GuardianError,guardian_error_handler);app.include_router(router)
    @app.middleware("http")
    async def context(request:Request,call_next):
        request.state.request_id=request.headers.get("X-Request-ID") or str(uuid4());response=await call_next(request);response.headers["X-Request-ID"]=request.state.request_id;HTTP_REQUESTS.labels(request.method,request.url.path,str(response.status_code)).inc();return response
    @app.get("/health/live")
    def live():return {"status":"ok"}
    @app.get("/health/ready")
    def ready():
        try:
            with engine.connect() as conn:conn.execute(text("SELECT 1"))
        except Exception as exc:raise GuardianError(503,"command.database_unavailable","Command database unavailable") from exc
        return {"status":"ready"}
    @app.get("/metrics")
    def metrics():payload,ct=render_metrics();return Response(content=payload,media_type=ct)
    return app
app=create_app()
