"""服务模板端到端行为测试（定律2/3/4 的落地验证）。"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from kernel.db import init_db
from kernel.idempotency import InMemoryIdempotencyStore
from kernel.outbox import OutboxMessage
from sqlalchemy import select

from app.config import ServiceSettings
from app.main import create_app

IDENT = {"X-User-Id": "u-1", "X-User-Roles": "user"}


@pytest.fixture
async def client():
    settings = ServiceSettings(
        app_env="test",
        log_level="ERROR",
        trust_proxy_headers=True,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings=settings, idempotency_store=InMemoryIdempotencyStore())
    await init_db(app.state.engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.app = app  # type: ignore[attr-defined]
        yield c
    await app.state.engine.dispose()


async def test_health(client):
    assert (await client.get("/health/live")).status_code == 200
    assert (await client.get("/health/ready")).status_code == 200


async def test_create_user_requires_auth(client):
    resp = await client.post("/v1/users", json={"email": "a@b.c", "display_name": "A"})
    assert resp.status_code == 401


async def test_create_user_and_outbox_staged(client):
    resp = await client.post(
        "/v1/users",
        json={"email": "a@b.c", "display_name": "Alice"},
        headers={**IDENT, "Idempotency-Key": "k-create-1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@b.c"
    assert body["vip_level"] == 0

    # 定律4：业务事务提交后 outbox 已登记（relay 未启动，仍为 pending）
    async with client.app.state.session_factory() as session:
        row = (await session.execute(select(OutboxMessage))).scalar_one()
        assert row.event_name == "user.created.v1"
        assert row.status == "pending"


async def test_get_own_user_ok(client):
    created = await client.post(
        "/v1/users", json={"email": "b@c.d", "display_name": "Bob"}, headers=IDENT
    )
    uid = created.json()["id"]
    resp = await client.get(f"/v1/users/{uid}", headers={"X-User-Id": uid, "X-User-Roles": "user"})
    assert resp.status_code == 200
    assert resp.json()["id"] == uid


async def test_get_other_user_forbidden(client):
    created = await client.post(
        "/v1/users", json={"email": "c@d.e", "display_name": "Carol"}, headers=IDENT
    )
    uid = created.json()["id"]
    resp = await client.get(
        f"/v1/users/{uid}", headers={"X-User-Id": "someone-else", "X-User-Roles": "user"}
    )
    assert resp.status_code == 403


async def test_idempotent_create(client):
    headers = {**IDENT, "Idempotency-Key": "same-key"}
    r1 = await client.post("/v1/users", json={"email": "x@y.z", "display_name": "X"}, headers=headers)
    r2 = await client.post("/v1/users", json={"email": "x@y.z", "display_name": "X"}, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json() == r2.json()


async def test_duplicate_email_returns_business_code(client):
    """业务错误码：重复邮箱 -> 409 EMAIL_ALREADY_EXISTS（前端据此分支）。"""
    payload = {"email": "dup@code.dev", "display_name": "Dup"}
    r1 = await client.post("/v1/users", json=payload, headers=IDENT)
    assert r1.status_code == 201
    r2 = await client.post("/v1/users", json=payload, headers={**IDENT, "Idempotency-Key": "dup-2"})
    assert r2.status_code == 409
    body = r2.json()
    assert body["code"] == "EMAIL_ALREADY_EXISTS"
    assert body["status"] == 409
    assert body["type"] == "/docs/errors#email_already_exists"


async def test_get_missing_user_returns_business_code(client):
    """业务错误码：用户不存在 -> 404 USER_NOT_FOUND。"""
    resp = await client.get(
        "/v1/users/00000000-0000-0000-0000-000000000000",
        headers={"X-User-Id": "u-1", "X-User-Roles": "user"},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "USER_NOT_FOUND"


async def test_errors_endpoint_exposes_service_codes(client):
    """服务业务码自动进入 /errors 清单（可生成前端枚举/文档）。"""
    resp = await client.get("/errors")
    assert resp.status_code == 200
    codes = {item["code"] for item in resp.json()["codes"]}
    assert "EMAIL_ALREADY_EXISTS" in codes
    assert "USER_NOT_FOUND" in codes