"""动态扩缩器入口：周期抓取目标服务指标 -> 策略判定 -> 执行扩容/缩容。

运行（宿主机，真实执行）：
    DRY_RUN=false TARGET_URLS=http://host:8100 python -m uvicorn autoscaler.main:app --port 8200
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from kernel.app import create_app as kernel_create_app

from .config import AutoscalerSettings
from .metrics import ServiceSample, compute_rps, extract_sample, parse_prometheus_text
from .policy import PolicyState, decide
from .scaler import ComposeScaler, NoopScaler

logger = logging.getLogger(__name__)

DECISIONS = {"hold": 0, "up": 0, "down": 0}


class ScalingController:
    def __init__(self, settings: AutoscalerSettings, scaler, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._scaler = scaler
        self._client = http_client
        self._prev: dict[str, ServiceSample] = {}
        self._state = PolicyState()
        self._replicas = max(len(settings.target_url_list), settings.min_replicas)

    async def tick(self) -> None:
        settings = self._settings
        urls = settings.target_url_list
        if not urls:
            logger.warning("未配置 TARGET_URLS，无法采集指标")
            return

        now = time.monotonic()
        totals = ServiceSample()
        for url in urls:
            try:
                resp = await self._client.get(f"{url.rstrip('/')}/metrics", timeout=5.0)
                if resp.status_code != 200:
                    logger.warning("指标抓取失败 %s -> %s", url, resp.status_code)
                    continue
                parsed = parse_prometheus_text(resp.text)
                sample = extract_sample(parsed, settings.target_service)
                totals.requests_total += sample.requests_total
                totals.error_total += sample.error_total
            except httpx.HTTPError as exc:
                logger.warning("指标抓取异常 %s: %s", url, exc)

        window = settings.interval_seconds
        rps_total, error_rate = compute_rps(now, self._prev.get("all"), totals, window)
        self._prev["all"] = totals
        rps_per_instance = rps_total / self._replicas if self._replicas else 0.0

        decision = decide(
            settings=settings,
            state=self._state,
            current_replicas=self._replicas,
            rps_per_instance=rps_per_instance,
            error_rate=error_rate,
            now=now,
        )
        logger.info(
            "扩缩容决策: %s | rps/实例=%.2f 错误率=%.2f%% 当前副本=%s | %s",
            decision.action.upper(),
            rps_per_instance,
            error_rate * 100,
            self._replicas,
            decision.reason,
        )
        DECISIONS[decision.action] += 1

        if decision.action == "up":
            target = min(self._replicas + 1, settings.max_replicas)
            await self._apply(settings.target_service, target)
        elif decision.action == "down":
            target = max(self._replicas - 1, settings.min_replicas)
            await self._apply(settings.target_service, target)

    async def _apply(self, service: str, target: int) -> None:
        await self._scaler.set_replicas(service, target)
        self._replicas = target


async def _run_loop(controller: ScalingController, interval: float) -> None:
    while True:
        try:
            await controller.tick()
        except Exception:
            logger.exception("扩缩容循环异常")
        await asyncio.sleep(interval)


def create_app(settings: AutoscalerSettings | None = None) -> FastAPI:
    settings = settings or AutoscalerSettings()
    scaler = ComposeScaler(settings.compose_dir, settings.compose_file, settings.compose_env_file) if not settings.dry_run else NoopScaler()
    http_client = httpx.AsyncClient(timeout=5.0)
    controller = ScalingController(settings, scaler, http_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(_run_loop(controller, settings.interval_seconds))
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await http_client.aclose()

    app = kernel_create_app(
        settings=settings,
        title="Dynamic Autoscaler",
        lifespan=lifespan,
        health_checks={},
    )
    app.state.controller = controller
    return app


app = create_app()