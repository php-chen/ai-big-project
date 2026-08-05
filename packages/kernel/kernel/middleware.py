"""请求上下文与身份中间件（定律3 + 定律5）。

RequestContextMiddleware：
- 生成/延续 request_id、trace_id（contextvars 传播，asyncio 安全）；
- 响应头回写 X-Request-ID。

IdentityMiddleware：
- 解析网关注入的可信头 X-User-Id / X-User-Roles / X-Tenant-Id；
- 仅当 TRUST_PROXY_HEADERS=true 时接受（生产须配合 mTLS/服务网格）；
- 否则一律视为未认证（默认拒绝）。
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from .context import Identity, set_identity, set_request_context
from .telemetry import get_tracer

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """纯 ASGI 中间件（同一 task 内执行，contextvars 对应用可见）。"""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.tracer = get_tracer("kernel.request-context")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        span_name = f"{scope.get('method', '')} {scope.get('path', '')}"

        with self.tracer.start_as_current_span(span_name) as span:
            ctx = span.get_span_context()
            if ctx.is_valid:
                trace_id = format(ctx.trace_id, "032x")
                span_id = format(ctx.span_id, "016x")
            else:
                trace_id, span_id = "", ""
            set_request_context(request_id, trace_id=trace_id, span_id=span_id)

            async def send_wrapper(message: dict) -> None:
                if message["type"] == "http.response.start":
                    raw_headers = list(message.get("headers", []))
                    raw_headers.append((b"x-request-id", request_id.encode("latin-1")))
                    message["headers"] = raw_headers
                await send(message)

            await self.app(scope, receive, send_wrapper)


class IdentityMiddleware:
    """解析网关注入的可信身份头（默认拒绝：不信任则视为未认证）。"""

    def __init__(self, app: Any, trust_proxy_headers: bool = False) -> None:
        self.app = app
        self.trust_proxy_headers = trust_proxy_headers

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        identity: Identity | None = None
        if self.trust_proxy_headers:
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            user_id = headers.get("x-user-id")
            if user_id:
                roles = tuple(r for r in headers.get("x-user-roles", "").split(",") if r)
                identity = Identity(
                    user_id=user_id,
                    roles=roles,
                    tenant_id=headers.get("x-tenant-id"),
                )
        set_identity(identity)
        await self.app(scope, receive, send)


class AccessLogMiddleware:
    """结构化访问日志（定律5）：method/path/status/duration_ms/client + 关联 ID。

    uvicorn 原生访问日志已由 setup_logging 关闭，统一走本中间件。
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.logger = logging.getLogger("kernel.access")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_holder: dict[str, Any] = {}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)
        duration_ms = (time.perf_counter() - start) * 1000

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        self.logger.info(
            "access",
            extra={
                "ctx": {
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status": status_holder.get("status"),
                    "duration_ms": round(duration_ms, 1),
                    "client_ip": headers.get("x-forwarded-for", "").split(",")[0].strip()
                    or headers.get("x-real-ip", ""),
                }
            },
        )