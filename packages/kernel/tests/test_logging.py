"""日志功能测试（定律5）：
- ContextFilter 自动注入 request_id/trace_id/用户身份；
- JsonFormatter 敏感字段脱敏；
- AccessLogMiddleware 输出结构化访问日志；
- enable_slow_query_logging 记录慢查询。
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from kernel.app import create_app
from kernel.config import Settings
from kernel.context import Identity, set_identity, set_request_context
from kernel.db import build_database_router, enable_slow_query_logging, init_db
from kernel.logging import ContextFilter, JsonFormatter


class CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _capture_logger(name: str) -> tuple[logging.Logger, CaptureHandler]:
    handler = CaptureHandler()
    handler.setFormatter(JsonFormatter(service_name="svc", app_env="test"))
    handler.addFilter(ContextFilter())
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False
    return logger, handler


def test_context_filter_injects_context_and_masks():
    set_request_context("req-1", trace_id="4bf92f3577b34da6a3ce929d0e0e4736", span_id="00f067aa0ba902b7")
    set_identity(Identity(user_id="u-9", tenant_id="t-1"))

    logger, handler = _capture_logger("test.logging")
    try:
        logger.info(
            "user login",
            extra={"ctx": {"order_id": "o-1", "password": "hunter2", "api_key": "secret-key", "user_id": "spoofed"}},
        )
    finally:
        logger.removeHandler(handler)

    payload = json.loads(handler.lines[0])
    assert payload["request_id"] == "req-1"
    assert payload["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert payload["service"] == "svc"
    assert payload["env"] == "test"
    # 内置键优先：user_id 来自身份上下文，业务 extra 无法覆盖
    assert payload["user_id"] == "u-9"
    # 脱敏
    assert payload["password"] == "***"
    assert payload["api_key"] == "***"
    # 业务字段正常
    assert payload["order_id"] == "o-1"


async def test_access_log_middleware():
    settings = Settings(app_env="test", log_level="ERROR", log_access=True)
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    app = create_app(settings=settings, title="log-test", routers=[router])

    access_logger, handler = _capture_logger("kernel.access")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ping", headers={"X-Request-ID": "req-acc"})
            assert resp.status_code == 200
    finally:
        access_logger.removeHandler(handler)

    payload = json.loads(handler.lines[-1])
    assert payload["method"] == "GET"
    assert payload["path"] == "/ping"
    assert payload["status"] == 200
    assert payload["duration_ms"] >= 0
    assert payload["request_id"] == "req-acc"


async def test_slow_query_logging():
    db = build_database_router("sqlite+aiosqlite:///:memory:")
    await init_db(db.write_engine)
    enable_slow_query_logging(db.write_engine, threshold_ms=0.0001, engine_role="write")

    slow_logger, handler = _capture_logger("kernel.db.slow")
    try:
        async with db.write_factory() as session:
            await session.execute(text("SELECT 1"))
    finally:
        slow_logger.removeHandler(handler)
        await db.dispose()

    assert handler.lines, "慢查询日志应被记录"
    payload = json.loads(handler.lines[0])
    assert "duration_ms" in payload
    assert payload["engine"] == "write"
    assert "SELECT" in payload["sql"].upper()