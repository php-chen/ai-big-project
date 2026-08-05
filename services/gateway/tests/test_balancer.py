"""UpstreamBalancer 测试：轮询 / 失败转移 / 全挂 / 半开恢复 / 5xx 剔除。"""
from __future__ import annotations

import asyncio

import httpx
import pytest
from kernel.errors import DownstreamError

from gateway_app.balancer import UpstreamBalancer


def _mock(handler) -> httpx.AsyncClient:
    return UpstreamBalancer(
        ["http://a:1", "http://b:1"],
        fail_threshold=1,
        transport=httpx.MockTransport(handler),
    )


async def test_round_robin():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, json={"ok": True})

    balancer = _mock(handler)
    try:
        for _ in range(4):
            resp = await balancer.request("GET", "/x", headers={})
            assert resp.status_code == 200
    finally:
        await balancer.close()

    assert seen == ["a", "b", "a", "b"], f"应轮询交替，实际 {seen}"


async def test_failover_on_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a":
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"ok": True})

    balancer = _mock(handler)
    try:
        resp = await balancer.request("GET", "/x", headers={})
    finally:
        await balancer.close()

    assert resp.status_code == 200
    snapshot = balancer.health_snapshot()
    assert snapshot["http://a:1"] is False
    assert snapshot["http://b:1"] is True


async def test_5xx_marks_down_and_failover():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a":
            return httpx.Response(500, json={"err": "boom"})
        return httpx.Response(200, json={"ok": True})

    balancer = _mock(handler)
    try:
        resp = await balancer.request("GET", "/x", headers={})
    finally:
        await balancer.close()

    assert resp.status_code == 200
    assert balancer.health_snapshot()["http://a:1"] is False


async def test_all_down_raises_downstream_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    balancer = _mock(handler)
    try:
        with pytest.raises(DownstreamError):
            await balancer.request("GET", "/x", headers={})
    finally:
        await balancer.close()


async def test_half_open_recovery():
    a_down = {"v": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a":
            if a_down["v"]:
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"ok": True})

    balancer = UpstreamBalancer(
        ["http://a:1", "http://b:1"],
        fail_threshold=1,
        cooldown_seconds=0.01,
        transport=httpx.MockTransport(handler),
    )
    try:
        await balancer.request("GET", "/x", headers={})
        assert balancer.health_snapshot()["http://a:1"] is False

        a_down["v"] = False
        await asyncio.sleep(0.03)  # 冷却期结束 -> 半开重试
        await balancer.request("GET", "/x", headers={})
        assert balancer.health_snapshot()["http://a:1"] is True
    finally:
        await balancer.close()