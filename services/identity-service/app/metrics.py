from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, generate_latest


class IdentityMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "guardian_identity_http_requests_total",
            "Total HTTP requests handled by the identity service",
            labelnames=("method", "path", "status"),
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)


def install_metrics(app: FastAPI) -> IdentityMetrics:
    metrics = IdentityMetrics()

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        metrics.http_requests.labels(
            method=request.method,
            path=route_path,
            status=str(response.status_code),
        ).inc()
        return response

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(content=metrics.render(), media_type=CONTENT_TYPE_LATEST)

    return metrics
