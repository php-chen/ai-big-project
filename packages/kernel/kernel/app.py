"""应用工厂（方向一/二：所有服务统一入口，保证基座一致）。

create_app 负责装配：日志、追踪、请求上下文、身份解析、异常处理、健康检查、幂等中间件、访问日志、业务路由。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, FastAPI

from .config import Settings, get_settings
from .health import register_health
from .idempotency import IdempotencyMiddleware, IdempotencyStore, build_idempotency_store
from .logging import setup_logging
from .metrics import MetricsMiddleware, metrics_router
from .middleware import AccessLogMiddleware, IdentityMiddleware, RequestContextMiddleware
from .problem import errors_router, register_exception_handlers
from .telemetry import setup_telemetry

Lifespan = Callable[[FastAPI], Any]


def create_app(
    *,
    settings: Settings | None = None,
    title: str | None = None,
    routers: Sequence[APIRouter] = (),
    lifespan: Lifespan | None = None,
    health_checks: dict[str, Callable[[], Awaitable[bool]]] | None = None,
    idempotency_store: IdempotencyStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    setup_logging(
        settings.log_level,
        json_logs=settings.log_json,
        service_name=settings.service_name,
        app_env=settings.app_env,
    )
    setup_telemetry(settings)

    app = FastAPI(
        title=title or f"{settings.app_name} {settings.service_name}",
        version="0.1.0",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    app.add_middleware(IdentityMiddleware, trust_proxy_headers=settings.trust_proxy_headers)
    app.add_middleware(RequestContextMiddleware)

    store = idempotency_store
    if store is None:
        store = build_idempotency_store(settings.redis_url, settings.idempotency_ttl_seconds)
    app.add_middleware(
        IdempotencyMiddleware,
        store=store,
        service=settings.service_name,
        ttl_seconds=settings.idempotency_ttl_seconds,
    )

    if settings.log_access:
        app.add_middleware(AccessLogMiddleware)

    # Prometheus 指标（定律5 + 动态扩容度量）
    app.add_middleware(MetricsMiddleware, service=settings.service_name)
    app.include_router(metrics_router())

    register_health(app, health_checks)
    app.include_router(errors_router())

    for router in routers:
        app.include_router(router)

    return app