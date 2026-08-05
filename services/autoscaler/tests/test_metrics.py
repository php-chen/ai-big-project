"""指标解析与 RPS 计算测试。"""
from __future__ import annotations

import httpx
import pytest

from autoscaler.main import ScalingController
from autoscaler.metrics import ServiceSample, compute_rps, extract_sample, parse_prometheus_text
from autoscaler.scaler import NoopScaler

TEXT = """# HELP http_requests_total HTTP 请求总数
# TYPE http_requests_total counter
http_requests_total{service="service-template",method="GET",path="/v1/users/{id}",status="200"} 10.0
http_requests_total{service="service-template",method="GET",path="/v1/users/{id}",status="500"} 2.0
http_requests_total{service="gateway",method="GET",path="/x",status="200"} 5.0
"""


def test_parse_and_extract():
    parsed = parse_prometheus_text(TEXT)
    sample = extract_sample(parsed, "service-template")
    assert sample.requests_total == 12.0
    assert sample.error_total == 2.0


def test_rps_delta():
    prev = ServiceSample(requests_total=10, error_total=2)
    curr = ServiceSample(requests_total=30, error_total=4)
    rps, err = compute_rps(now=5.0, prev=prev, curr=curr, window_seconds=5.0)
    assert rps == 4.0  # (30-10)/5
    assert err == pytest.approx(2 / 20)


def test_first_sample_zero():
    rps, err = compute_rps(now=5.0, prev=None, curr=ServiceSample(requests_total=10), window_seconds=5.0)
    assert rps == 0.0
    assert err == 0.0


class RecordingScaler(NoopScaler):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def set_replicas(self, service: str, count: int) -> None:
        self.calls.append((service, count))


def _body(count: float, service: str) -> str:
    return f'http_requests_total{{service="{service}",method="GET",path="/x",status="200"}} {count}'


async def test_controller_dry_run_scales_up():
    from autoscaler.config import AutoscalerSettings

    settings = AutoscalerSettings(
        app_env="test",
        log_level="ERROR",
        target_urls="http://fake:1",
        target_service="svc",
        interval_seconds=5.0,
        scale_up_rps=1,
        sustain_up=1,
        cooldown_seconds=0,
        max_replicas=5,
    )
    counter = {"n": 10}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 20
        return httpx.Response(200, text=_body(counter["n"], "svc"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    scaler = RecordingScaler()
    controller = ScalingController(settings, scaler, client)
    try:
        await controller.tick()  # 首样本：rps=0
        await controller.tick()  # 第二次：delta=20 -> rps=4 > 1 -> 扩容
    finally:
        await client.aclose()

    assert scaler.calls == [("svc", 2)]