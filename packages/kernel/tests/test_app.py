"""内核应用装配行为测试：默认拒绝 / Problem Details / 健康检查 / 身份注入。"""
from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient

from kernel.app import create_app
from kernel.auth import get_current_identity
from kernel.config import Settings


def make_app(trust_proxy: bool = False, **overrides) -> object:
    settings = Settings(app_env="test", log_level="WARNING", trust_proxy_headers=trust_proxy, **overrides)
    router = APIRouter()

    @router.get("/me")
    async def me(identity=Depends(get_current_identity)) -> dict:
        return {
            "user_id": identity.user_id,
            "roles": list(identity.roles),
            "tenant_id": identity.tenant_id,
        }

    async def db_ok() -> bool:
        return True

    return create_app(settings=settings, title="kernel-test", routers=[router], health_checks={"db": db_ok})


@pytest.fixture
async def client():
    app = make_app(trust_proxy=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_ready(client):
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_default_deny_without_identity():
    app = make_app(trust_proxy=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/me")
        assert resp.status_code == 401
        assert resp.headers["content-type"].startswith("application/problem+json")
        assert resp.json()["code"] == "UNAUTHORIZED"


async def test_identity_injected_when_trusted(client):
    resp = await client.get(
        "/me",
        headers={"X-User-Id": "u-1", "X-User-Roles": "user,admin", "X-Tenant-Id": "t-1"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "u-1", "roles": ["user", "admin"], "tenant_id": "t-1"}


async def test_unknown_route_returns_problem(client):
    resp = await client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_request_id_is_set_on_response(client):
    resp = await client.get("/health/live", headers={"X-Request-ID": "req-123"})
    assert resp.headers.get("x-request-id") == "req-123"