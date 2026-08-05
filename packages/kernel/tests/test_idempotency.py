"""幂等中间件测试（定律4：副作用接口必须幂等）。"""
from __future__ import annotations

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from kernel.app import create_app
from kernel.config import Settings
from kernel.idempotency import InMemoryIdempotencyStore


@pytest.fixture
async def client():
    calls = {"n": 0}
    store = InMemoryIdempotencyStore()
    router = APIRouter()

    @router.post("/orders")
    async def create_order(payload: dict) -> dict:
        calls["n"] += 1
        return {"order_id": f"o-{calls['n']}", "item": payload.get("item")}

    settings = Settings(app_env="test", log_level="WARNING")
    app = create_app(settings=settings, title="idem-test", routers=[router], idempotency_store=store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.calls = calls  # type: ignore[attr-defined]
        yield c


async def test_replay_same_key(client):
    headers = {"Idempotency-Key": "k-1"}
    r1 = await client.post("/orders", json={"item": "a"}, headers=headers)
    r2 = await client.post("/orders", json={"item": "a"}, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()
    assert client.calls["n"] == 1  # type: ignore[attr-defined]


async def test_different_keys_execute_separately(client):
    await client.post("/orders", json={"item": "a"}, headers={"Idempotency-Key": "k-1"})
    await client.post("/orders", json={"item": "b"}, headers={"Idempotency-Key": "k-2"})
    assert client.calls["n"] == 2  # type: ignore[attr-defined]