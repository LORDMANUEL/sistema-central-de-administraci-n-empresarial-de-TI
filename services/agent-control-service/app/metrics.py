from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

HTTP_REQUESTS = Counter("guardian_agent_control_http_requests_total", "HTTP requests", ["method", "path", "status"])
HEARTBEATS = Counter("guardian_agent_control_heartbeats_total", "Accepted heartbeats")


def render_metrics():
    return generate_latest(), CONTENT_TYPE_LATEST
