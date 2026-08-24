from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

HTTP_REQUESTS = Counter(
    "it_guardian_asset_http_requests_total",
    "Total HTTP requests handled by Asset Service",
    ["method", "path", "status"],
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
