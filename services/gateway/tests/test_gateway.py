"""网关测试（定律3：功能白名单默认拒绝；定律5：trace 透传；LB：客户端侧轮询）。"""
from __future__ import annotations

from typing import ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway_app.config import GatewaySettings
from gateway_app.main import create_app

TOKEN = {"Authorization": "Bearer dev-token"}


@pytest.fixture
def client():
    settings = GatewaySettings(
        app_env="test",
        log_level="ERROR",
        upstream_service_url="http://127.0.0.1:59999",  # 不存在，用于测 502
        dev_token="dev-token",
    )
    return TestClient(create_app(settings=settings))


def test_health(client):
    assert client.get("/health/live").status_code == 200


def test_missing_token_unauthorized(client):
    resp = client.get("/v1/users/u-1")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_invalid_token_unauthorized(client):
    resp = client.get("/v1/users/u-1", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_non_whitelisted_method_forbidden(client):
    resp = client.request("DELETE", "/v1/users/u-1", headers=TOKEN)
    assert resp.status_code == 403


def test_upstream_down_returns_bad_gateway(client):
    resp = client.get("/v1/users/u-1", headers=TOKEN)
    assert resp.status_code == 502
    assert resp.json()["code"] == "BAD_GATEWAY"


def test_proxy_injects_identity_and_trace(monkeypatch):
    """经 balancer 转发：身份注入 + trace 透传 + 客户端侧 LB。"""
    captured: dict = {}

    class FakeResponse:
        content = b'{"id":"u-1","ok":true}'
        status_code = 200
        headers: ClassVar[dict] = {"content-type": "application/json"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def request(self, method, url, headers=None, content=None):
            captured.update(method=method, url=url, headers=headers or {}, content=content)
            return FakeResponse()

        async def get(self, url, timeout=None):
            return FakeResponse()

        async def aclose(self):
            pass

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    settings = GatewaySettings(
        app_env="test",
        log_level="ERROR",
        upstream_service_urls="http://upstream-a:8100,http://upstream-b:8100",
        dev_token="dev-token",
    )
    with TestClient(create_app(settings=settings)) as client:
        resp = client.get(
            "/v1/users/u-1",
            headers={
                **TOKEN,
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            },
        )
    assert resp.status_code == 200
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/v1/users/u-1")
    assert captured["headers"]["X-User-Id"] == "dev-user"
    assert captured["headers"]["X-User-Roles"] == "user,admin"
    assert captured["headers"]["X-Tenant-Id"] == "dev-tenant"
    assert "traceparent" in captured["headers"]