from prometheus_client import CONTENT_TYPE_LATEST,Counter,generate_latest
HTTP_REQUESTS=Counter("guardian_command_http_requests_total","HTTP requests",["method","path","status"])
def render_metrics():return generate_latest(),CONTENT_TYPE_LATEST
