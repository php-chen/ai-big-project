"""网关客户端侧负载均衡（网关 -> 服务副本）。

- 轮询（round-robin）选择健康实例；
- 健康感知：连接错误 / 5xx 连续达阈值标记不可用；冷却期后半开重试，成功即恢复；
- 共享 httpx.AsyncClient（连接池复用 keep-alive）；
- refresh()：动态更新实例池（动态扩容：新增/下线副本自动被感知）；
- 响应头 X-Upstream 标记实际命中的实例（可观测性）。
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from typing import Any

import httpx
from kernel.errors import DownstreamError

logger = logging.getLogger(__name__)


class UpstreamBalancer:
    def __init__(
        self,
        urls: list[str],
        *,
        timeout: float = 10.0,
        fail_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        transport: Any = None,
    ) -> None:
        self._urls = list(urls)
        self._timeout = timeout
        self._fail_threshold = fail_threshold
        self._cooldown = cooldown_seconds
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self._states: dict[str, dict[str, Any]] = {
            url: {"healthy": True, "fails": 0, "down_since": None} for url in self._urls
        }
        self._rr = itertools.cycle(range(len(self._urls)))

    @property
    def urls(self) -> list[str]:
        return list(self._urls)

    def refresh(self, urls: list[str]) -> None:
        """动态更新实例池：保留仍存在实例的健康状态，加入新实例，移除已下线实例。"""
        if not urls:
            return
        urls = list(dict.fromkeys(urls))  # 去重（注册中心可能返回重复地址）
        new_states: dict[str, dict[str, Any]] = {}
        for url in urls:
            if url in self._states:
                new_states[url] = self._states[url]
            else:
                new_states[url] = {"healthy": True, "fails": 0, "down_since": None}
        self._states = new_states
        self._urls = urls
        self._rr = itertools.cycle(range(len(self._urls)))

    def health_snapshot(self) -> dict[str, bool]:
        return {url: state["healthy"] for url, state in self._states.items()}

    def _is_available(self, url: str) -> bool:
        state = self._states[url]
        if state["healthy"]:
            return True
        # 半开：冷却期后允许一次探活请求
        return state["down_since"] is not None and (time.monotonic() - state["down_since"]) >= self._cooldown

    def _next(self) -> str:
        for _ in range(len(self._urls)):
            url = self._urls[next(self._rr)]
            if self._is_available(url):
                return url
        raise DownstreamError("所有上游服务实例均不可用")

    def _record_success(self, url: str) -> None:
        state = self._states[url]
        if not state["healthy"]:
            logger.info("上游实例恢复: %s", url)
        state.update(healthy=True, fails=0, down_since=None)

    def _record_failure(self, url: str) -> None:
        state = self._states[url]
        state["fails"] += 1
        if state["fails"] >= self._fail_threshold:
            if state["healthy"]:
                logger.warning("上游实例标记不可用: %s (连续失败 %s 次)", url, state["fails"])
            state.update(healthy=False, down_since=time.monotonic())

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        content: bytes | None = None,
    ) -> httpx.Response:
        """按健康轮询选择一个实例发起请求；失败自动 failover 到下一健康实例。"""
        last_error: Exception | None = None
        tried: set[str] = set()
        for _ in range(len(self._urls)):
            url = self._next()
            if url in tried:
                break
            tried.add(url)
            logger.debug("upstream 选择: %s", url)
            try:
                resp = await self._client.request(
                    method,
                    f"{url.rstrip('/')}/{path.lstrip('/')}",
                    headers=headers,
                    content=content,
                )
                if resp.status_code >= 500:
                    self._record_failure(url)
                    last_error = DownstreamError(f"上游 {url} 返回 {resp.status_code}")
                    continue
                self._record_success(url)
                resp.headers["x-upstream"] = url  # 可观测性：标记实际命中的实例
                return resp
            except httpx.HTTPError as exc:
                self._record_failure(url)
                last_error = exc
        raise DownstreamError(f"所有上游实例均不可用: {last_error}") from last_error

    async def probe_all(self) -> None:
        """后台健康探测：把冷却期结束的不可用实例恢复为健康。"""
        for url in self._urls:
            state = self._states[url]
            if state["healthy"]:
                continue
            try:
                resp = await self._client.get(f"{url.rstrip('/')}/health/live", timeout=self._timeout)
                if resp.status_code < 500:
                    self._record_success(url)
            except httpx.HTTPError:
                state["down_since"] = time.monotonic()

    async def close(self) -> None:
        await self._client.aclose()


async def probe_loop(balancer: UpstreamBalancer, interval_seconds: float = 5.0) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await balancer.probe_all()
        except Exception:
            logger.exception("上游健康探测异常")