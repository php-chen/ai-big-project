"""OpenTelemetry 追踪基座（定律5：W3C traceparent 标准，禁止自造 TraceID 头）。

- 通过环境变量 OTEL_EXPORTER_OTLP_ENDPOINT 配置导出端点（留空 = 关闭导出，使用 no-op tracer）；
- 生产环境必须接入 OTLP Collector；
- asyncio 下由 contextvars 传播（见 middleware.py / context.py）。
"""
from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

from .config import Settings

logger = logging.getLogger(__name__)

# W3C Trace Context 传播器：不同 OTel 版本模块位置不同，兼容两者
try:
    from opentelemetry.propagators.tracecontext import TraceContextTextMapPropagator
except ModuleNotFoundError:  # OTel >= 1.44 位置变更
    from opentelemetry.trace.propagation.tracecontext import (  # type: ignore[no-redef]
        TraceContextTextMapPropagator,
    )

TRACE_PROPAGATOR = TraceContextTextMapPropagator()


def setup_telemetry(settings: Settings) -> None:
    """按配置初始化 TracerProvider。端点未配置时保持 no-op（测试/本地零噪音）。"""
    endpoint = settings.otel_exporter_otlp_endpoint
    if not endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: settings.otel_service_name or settings.service_name})
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")))
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry OTLP 追踪已启用: %s", endpoint)
    except Exception:  # pragma: no cover - 导入失败不应阻断服务启动
        logger.warning("OpenTelemetry 初始化失败，使用 no-op tracer", exc_info=True)


def get_tracer(name: str = "ai-big-project") -> trace.Tracer:
    return trace.get_tracer(name)


def extract_trace_context(headers: dict[str, str]) -> Any:
    """从请求头提取 W3C trace 上下文（网关透传使用）。"""
    return TRACE_PROPAGATOR.extract(headers)


def inject_trace_headers(carrier: dict[str, str]) -> None:
    """把当前 span 的 trace 上下文注入到出站请求头（网关/聚合层使用）。"""
    TRACE_PROPAGATOR.inject(carrier)