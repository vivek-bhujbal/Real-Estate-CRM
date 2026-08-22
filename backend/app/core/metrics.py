"""Low-cardinality HTTP metrics for Prometheus-compatible collectors."""

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "estateops_http_requests_total",
    "Completed HTTP requests",
    labelnames=("method", "route", "status_code"),
)
HTTP_DURATION = Histogram(
    "estateops_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def observe_request(method: str, route: str, status_code: int, duration: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status_code=str(status_code)).inc()
    HTTP_DURATION.labels(method=method, route=route).observe(duration)
