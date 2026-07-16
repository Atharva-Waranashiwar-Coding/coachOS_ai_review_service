"""HTTP request logging, request IDs, and Prometheus metrics."""

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.core.config import settings
from app.core.logging import request_id_context

REQUESTS = Counter(
    "coachos_http_requests_total",
    "Total HTTP requests.",
    ("service", "method", "route", "status"),
)
LATENCY = Histogram(
    "coachos_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("service", "method", "route"),
)
IN_PROGRESS = Gauge(
    "coachos_http_requests_in_progress",
    "HTTP requests currently being processed.",
    ("service", "method"),
)


def register_observability(app: FastAPI) -> None:
    """Register request middleware and the Prometheus scrape endpoint."""
    logger = logging.getLogger("coachos.http")

    @app.middleware("http")
    async def observe_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(settings.request_id_header) or str(uuid4())
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        status_code = 500
        IN_PROGRESS.labels(settings.app_name, request.method).inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[settings.request_id_header] = request_id
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            duration = time.perf_counter() - started
            REQUESTS.labels(settings.app_name, request.method, route, str(status_code)).inc()
            LATENCY.labels(settings.app_name, request.method, route).observe(duration)
            IN_PROGRESS.labels(settings.app_name, request.method).dec()
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            request_id_context.reset(token)

    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
