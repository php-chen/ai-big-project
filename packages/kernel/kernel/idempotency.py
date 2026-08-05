"""幂等存储与中间件（定律4：副作用接口必须幂等）。

- RedisIdempotencyStore：生产环境（Redis SET NX + TTL）；
- InMemoryIdempotencyStore：开发/测试（进程内，重启即失效——生产禁用）；
- 服务必须通过 Idempotency-Key 头声明幂等键。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def put(self, key: str, value: str, ttl_seconds: int) -> None: ...

    async def acquire(self, key: str, ttl_seconds: int) -> bool: ...


class RedisIdempotencyStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 3600) -> None:
        import redis.asyncio as aioredis

        self._redis: Any = aioredis.from_url(redis_url, decode_responses=True)
        self._default_ttl = ttl_seconds

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def put(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        await self._redis.set(key, value, ex=ttl_seconds or self._default_ttl)

    async def acquire(self, key: str, ttl_seconds: int | None = None) -> bool:
        return bool(await self._redis.set(key, "processing", nx=True, ex=ttl_seconds or self._default_ttl))

    async def close(self) -> None:
        await self._redis.aclose()


class InMemoryIdempotencyStore:
    """进程内实现（测试/无 Redis 的开发环境；生产禁止）。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def put(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._data[key] = value

    async def acquire(self, key: str, ttl_seconds: int | None = None) -> bool:
        if key in self._data:
            return False
        self._data[key] = "processing"
        return True

    async def close(self) -> None:
        self._data.clear()


def build_idempotency_store(redis_url: str | None, ttl_seconds: int = 3600) -> IdempotencyStore:
    if redis_url:
        try:
            return RedisIdempotencyStore(redis_url, ttl_seconds)
        except Exception:
            logger.warning("Redis 不可用，幂等存储降级为进程内实现（生产环境禁止）", exc_info=True)
    logger.warning("未配置 REDIS_URL，幂等存储使用进程内实现（生产环境禁止）")
    return InMemoryIdempotencyStore()


def make_idempotency_key(service: str, method: str, path: str, key: str) -> str:
    return f"idem:{service}:{method}:{path}:{key}"


class IdempotencyMiddleware:
    """HTTP 幂等中间件：读取 Idempotency-Key，重复请求直接返回首次结果。

    仅对 POST/PUT/PATCH 生效；无 Idempotency-Key 头时直接放行。
    """

    def __init__(self, app: Any, store: IdempotencyStore, service: str = "service", ttl_seconds: int = 3600) -> None:
        self.app = app
        self.store = store
        self.service = service
        self.ttl_seconds = ttl_seconds

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        if method not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        idem_key = headers.get("idempotency-key")
        if not idem_key:
            await self.app(scope, receive, send)
            return

        key = make_idempotency_key(self.service, method, scope.get("path", ""), idem_key)
        cached = await self.store.get(key)
        if cached:
            payload = json.loads(cached)
            response = _json_response(payload["status"], payload["body"], payload.get("content_type", "application/json"))
            await response(scope, receive, send)
            return

        status_holder: dict[str, Any] = {}
        body_holder: dict[str, Any] = {}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body_holder["body"] = body_holder.get("body", b"") + (message.get("body") or b"")
                if not message.get("more_body", False):
                    await self.store.put(
                        key,
                        json.dumps(
                            {
                                "status": status_holder.get("status", 200),
                                "body": body_holder["body"].decode("utf-8", errors="replace"),
                                "content_type": _content_type(status_holder.get("headers", [])),
                            }
                        ),
                        self.ttl_seconds,
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _content_type(headers: list[tuple[bytes, bytes]]) -> str:
    for k, v in headers:
        if k.lower() == b"content-type":
            return v.decode("latin-1")
    return "application/json"


def _json_response(status: int, body: str, content_type: str):
    from starlette.responses import JSONResponse

    return JSONResponse(status_code=status, content=json.loads(body), media_type=content_type)