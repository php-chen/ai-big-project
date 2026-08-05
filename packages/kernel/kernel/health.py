"""健康检查（定律5：每个服务必须暴露 live + ready）。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Response

CheckFn = Callable[[], Awaitable[bool]]


def liveness_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    return router


def readiness_router(checks: dict[str, CheckFn]) -> APIRouter:
    router = APIRouter()

    @router.get("/health/ready", tags=["health"])
    async def ready(response: Response) -> dict[str, Any]:
        results: dict[str, str] = {}
        all_ok = True
        for name, check in checks.items():
            try:
                ok = await check()
            except Exception:  # noqa: BLE001 - 依赖检查有意捕获所有异常
                ok = False
            results[name] = "ok" if ok else "unavailable"
            all_ok = all_ok and ok
        if not all_ok:
            response.status_code = 503
        return {"status": "ok" if all_ok else "degraded", "checks": results}

    return router


def register_health(app: Any, checks: dict[str, CheckFn] | None = None) -> None:
    """注册 live + ready（ready 带依赖检查）。"""
    app.include_router(liveness_router())
    app.include_router(readiness_router(checks or {}))