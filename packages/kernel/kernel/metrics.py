"""Prometheus 指标基座（定律5 + 动态扩容的度量基础）。

- /metrics 暴露 Prometheus 文本格式：请求量 / 错误率 / 延迟直方图 / 在途请求；
- MetricsMiddleware 自动统计每个请求；
- 自动扩缩器（services/autoscaler）据此判定扩缩容。
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "HTTP 请求总数",
    ["service", "method", "path", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["service", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_REQUESTS_IN_FLIGHT = Gauge("http_requests_in_flight", "在途请求数", ["service"])


class MetricsMiddleware:
    """请求指标采集：计数 + 耗时直方图 + 在途请求。"""

    def __init__(self, app: Any, service: str = "service") -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = _metric_path(scope.get("path", ""))
        HTTP_REQUESTS_IN_FLIGHT.labels(self.service).inc()
        start = time.perf_counter()
        status_holder: dict[str, Any] = {}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            status = status_holder.get("status", 500)
            HTTP_REQUESTS_TOTAL.labels(self.service, method, path, str(status)).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(self.service, method, path).observe(duration)
            HTTP_REQUESTS_IN_FLIGHT.labels(self.service).dec()


def _metric_path(path: str) -> str:
    """路径归一化：/v1/users/{id} -> /v1/users/{id}（避免指标基数爆炸）。"""
    import re

    return re.sub(r"/[0-9a-fA-F-]{8,}", "/{id}", path)


def metrics_router() -> APIRouter:
    router = APIRouter(tags=["metrics"])

    @router.get("/metrics")
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return router