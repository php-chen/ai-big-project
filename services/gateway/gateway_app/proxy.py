"""反向代理 + 身份注入 + trace 透传（定律3 + 定律5）+ 客户端侧负载均衡。"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response
from kernel.context import Identity
from kernel.telemetry import TRACE_PROPAGATOR, get_tracer
from opentelemetry import context as otel_context

from .balancer import UpstreamBalancer

TRACER = get_tracer("gateway")


async def proxy_request(
    method: str,
    path: str,
    request: Request,
    balancer: UpstreamBalancer,
    identity: Identity,
) -> Response:
    body = await request.body()

    # 定律5：提取入站 traceparent -> 起子 span -> 注入出站头
    carrier = {k: v for k, v in request.headers.items()}
    ctx = TRACE_PROPAGATOR.extract(carrier)
    token = otel_context.attach(ctx)
    try:
        with TRACER.start_as_current_span(f"gateway {method} {path}") as span:
            span.set_attribute("http.target", path)
            out_headers: dict[str, str] = {
                # 身份注入（定律3）：下游业务服务只信任这些头
                "X-User-Id": identity.user_id or "",
                "X-User-Roles": ",".join(identity.roles),
                "X-Tenant-Id": identity.tenant_id or "",
            }
            if body:
                out_headers["Content-Type"] = request.headers.get("content-type") or "application/json"
            TRACE_PROPAGATOR.inject(out_headers)

            # 客户端侧 LB：轮询健康实例，失败自动 failover（见 balancer.py）
            resp = await balancer.request(method, path, headers=out_headers, content=body or None)
    finally:
        otel_context.detach(token)

    headers = {"content-type": resp.headers.get("content-type", "application/json")}
    if "x-upstream" in resp.headers:
        headers["x-upstream"] = resp.headers["x-upstream"]
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=headers,
    )