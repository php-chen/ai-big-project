"""状态编码体系测试：三层模型（HTTP 状态 / 业务码 / 明细）。

- 注册表：内置码 + 自定义业务码；
- RFC 9457：type(文档链接) / code / detail / trace_id / X-Error-Code；
- 429 retry_after；422 字段级 errors；未知异常脱敏。
"""
from __future__ import annotations

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from kernel.app import create_app
from kernel.config import Settings
from kernel.error_codes import ErrorCode, get_error_code, register_error_code
from kernel.errors import ConflictError, NotFoundError, RateLimitError

# 自定义业务错误码示例（模块级注册，幂等）
register_error_code(ErrorCode("I_AM_A_TEAPOT", 418, "I'm a teapot", "短时间无法泡咖啡"))


class EchoIn(BaseModel):
    name: str


def make_app():
    settings = Settings(app_env="test", log_level="ERROR", service_name="codes")
    router = APIRouter()

    @router.get("/not-found")
    async def nf():
        raise NotFoundError()

    @router.get("/teapot")
    async def teapot():
        raise ConflictError(code="I_AM_A_TEAPOT", message="茶壶模式")

    @router.get("/rate")
    async def rate():
        raise RateLimitError(retry_after=30)

    @router.post("/echo")
    async def echo(payload: EchoIn):
        return {"name": payload.name}

    @router.get("/boom")
    async def boom():
        raise RuntimeError("内部敏感细节不应泄露")

    return create_app(settings=settings, title="codes", routers=[router])


async def test_builtin_registry():
    assert get_error_code("NOT_FOUND").http_status == 404
    assert get_error_code("RATE_LIMITED").retryable is True
    assert get_error_code("UNAUTHORIZED").http_status == 401


async def test_not_found_problem():
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/not-found")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "NOT_FOUND"
    assert body["type"] == "/docs/errors#not_found"
    assert body["instance"] == "/not-found"
    assert "trace_id" in body
    assert resp.headers.get("x-error-code") == "NOT_FOUND"
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_custom_business_code():
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/teapot")
    assert resp.status_code == 418
    body = resp.json()
    assert body["code"] == "I_AM_A_TEAPOT"
    assert body["detail"] == "茶壶模式"


async def test_rate_limit_retry_after():
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/rate")
    assert resp.status_code == 429
    assert resp.json()["code"] == "RATE_LIMITED"
    assert resp.json()["retry_after"] == 30


async def test_validation_errors_array():
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/echo", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert isinstance(body["errors"], list) and body["errors"]


async def test_unknown_exception_masked():
    app = make_app()
    # Starlette 1.x：ServerErrorMiddleware 发送 500 响应后重抛（供服务器记日志）；
    # 测试客户端用 raise_app_exceptions=False 拿回已发送的响应。
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "内部敏感细节" not in resp.text


async def test_errors_endpoint_lists_registry():
    app = make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/errors")
    assert resp.status_code == 200
    codes = {item["code"] for item in resp.json()["codes"]}
    assert "NOT_FOUND" in codes
    assert "I_AM_A_TEAPOT" in codes