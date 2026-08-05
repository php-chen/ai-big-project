"""服务注册中心（动态扩容的实例清单，供网关动态发现）。

- RedisServiceRegistry：实例以 `svc:reg:<service>:<instance_id>` 键 + TTL 心跳登记；
- LocalServiceRegistry：进程内实现（开发/测试，Redis 不可用时降级）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ServiceRegistry(Protocol):
    async def register(self, service: str, instance_id: str, url: str, ttl_seconds: int = 30) -> None: ...

    async def deregister(self, service: str, instance_id: str) -> None: ...

    async def list(self, service: str) -> list[str]: ...

    async def close(self) -> None: ...


class RedisServiceRegistry:
    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        self._redis: Any = aioredis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def _key(service: str, instance_id: str) -> str:
        return f"svc:reg:{service}:{instance_id}"

    async def register(self, service: str, instance_id: str, url: str, ttl_seconds: int = 30) -> None:
        await self._redis.set(self._key(service, instance_id), url, ex=ttl_seconds)

    async def deregister(self, service: str, instance_id: str) -> None:
        await self._redis.delete(self._key(service, instance_id))

    async def list(self, service: str) -> list[str]:
        keys = [k async for k in self._redis.scan_iter(match=f"svc:reg:{service}:*")]
        urls: list[str] = []
        for key in keys:
            value = await self._redis.get(key)
            if value:
                urls.append(value)
        return urls

    async def close(self) -> None:
        await self._redis.aclose()


class LocalServiceRegistry:
    """进程内实现（测试/无 Redis 的开发环境；生产必须用 Redis）。"""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, tuple[str, float]]] = {}

    async def register(self, service: str, instance_id: str, url: str, ttl_seconds: int = 30) -> None:
        self._data.setdefault(service, {})[instance_id] = (url, time.monotonic() + ttl_seconds)

    async def deregister(self, service: str, instance_id: str) -> None:
        self._data.get(service, {}).pop(instance_id, None)

    async def list(self, service: str) -> list[str]:
        now = time.monotonic()
        bucket = self._data.get(service, {})
        expired = [iid for iid, (_url, until) in bucket.items() if until < now]
        for iid in expired:
            bucket.pop(iid, None)
        return [url for iid, (url, until) in bucket.items() if until >= now]

    async def close(self) -> None:
        self._data.clear()


def build_registry(redis_url: str | None) -> ServiceRegistry:
    if redis_url:
        try:
            return RedisServiceRegistry(redis_url)
        except Exception:
            logger.warning("Redis 不可用，服务注册中心降级为进程内实现（生产环境禁止）", exc_info=True)
    return LocalServiceRegistry()


async def run_heartbeat(
    registry: ServiceRegistry,
    service: str,
    instance_id: str,
    url: str,
    ttl_seconds: int = 30,
    interval_seconds: float = 10.0,
) -> None:
    """实例心跳循环：持续登记自己，直到被取消。"""
    while True:
        try:
            await registry.register(service, instance_id, url, ttl_seconds)
        except Exception:  # noqa: BLE001 - 心跳失败不应中断
            logger.warning("服务注册心跳失败: %s/%s", service, instance_id)
        await asyncio.sleep(interval_seconds)