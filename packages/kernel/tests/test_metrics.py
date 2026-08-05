"""指标基座测试：/metrics 暴露 Prometheus 格式 + 请求指标采集。"""
from __future__ import annotations

from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from kernel.app import create_app
from kernel.config import Settings


async def test_metrics_endpoint_and_middleware():
    settings = Settings(app_env="test", log_level="ERROR", service_name="svc-test")
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    app = create_app(settings=settings, title="metrics-test", routers=[router])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ping")
        assert resp.status_code == 200

        metrics = await client.get("/metrics")
        assert metrics.status_code == 200
        text = metrics.text
        assert "http_requests_total" in text
        assert "http_request_duration_seconds" in text
        assert 'service="svc-test"' in text
        assert 'status="200"' in text