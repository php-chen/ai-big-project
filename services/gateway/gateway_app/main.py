from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kernel.app import create_app as kernel_create_app
from kernel.registry import ServiceRegistry, build_registry

from .balancer import UpstreamBalancer, probe_loop
from .config import GatewaySettings
from .middleware import FunctionWhitelistMiddleware
from .routes import router

logger = logging.getLogger(__name__)


async def _discovery_loop(
    registry: ServiceRegistry,
    balancer: UpstreamBalancer,
    service: str,
    interval_seconds: float = 5.0,
) -> None:
    """动态发现：定期从注册中心刷新上游实例池（扩缩容自动被感知）。"""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            urls = await registry.list(service)
            if urls:
                balancer.refresh(urls)
        except Exception:
            logger.exception("服务发现刷新异常")


def _lifespan(balancer: UpstreamBalancer, registry: ServiceRegistry | None, discovery_service: str):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = [asyncio.create_task(probe_loop(balancer))]
        if registry is not None and discovery_service:
            tasks.append(asyncio.create_task(_discovery_loop(registry, balancer, discovery_service)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await balancer.close()
            if registry is not None:
                await registry.close()

    return lifespan


def create_app(settings: GatewaySettings | None = None) -> FastAPI:
    settings = settings or GatewaySettings()
    balancer = UpstreamBalancer(settings.upstream_list, timeout=settings.upstream_timeout)
    registry = build_registry(settings.registry_url)
    app = kernel_create_app(
        settings=settings,
        title="API Gateway",
        routers=[router],
        lifespan=_lifespan(balancer, registry, settings.discovery_service),
        health_checks={},
    )
    # 白名单校验放在最外层（路由之前）：默认拒绝
    app.add_middleware(FunctionWhitelistMiddleware, settings=settings)
    app.state.settings = settings
    app.state.balancer = balancer
    app.state.registry = registry
    return app


app = create_app()