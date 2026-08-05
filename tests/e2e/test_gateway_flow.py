"""端到端测试 · 跨服务边界（网关 -> 模板服务）。

自动启动两个 uvicorn 子进程，验证 5 条定律在真实 HTTP 链路上的表现：
- 功能级鉴权（无 token -> 401；白名单外 -> 403）
- 身份注入 + 数据级授权（本人 200 / 他人 403 / admin 200）
- 幂等（同一 Idempotency-Key 只执行一次）
- 请求 ID 回写

运行：pytest -m e2e（或 scripts/test.ps1 -Level e2e）
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

pytestmark = pytest.mark.e2e

AUTH = {"Authorization": "Bearer dev-token"}
TRACE = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(base_url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{base_url}/health/live", timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def stack():
    template_port = _free_port()
    gateway_port = _free_port()

    tpl_env = dict(os.environ)
    tpl_env.update({"LOG_LEVEL": "WARNING", "TRUST_PROXY_HEADERS": "true"})
    template = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(template_port)],
        cwd=REPO_ROOT / "services" / "service-template",
        env=tpl_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    gw_env = dict(os.environ)
    gw_env.update(
        {
            "LOG_LEVEL": "WARNING",
            "UPSTREAM_SERVICE_URL": f"http://127.0.0.1:{template_port}",
            "DEV_TOKEN": "dev-token",
        }
    )
    gateway = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "gateway_app.main:app", "--host", "127.0.0.1", "--port", str(gateway_port)],
        cwd=REPO_ROOT / "services" / "gateway",
        env=gw_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        t_ok = _wait_health(f"http://127.0.0.1:{template_port}")
        g_ok = _wait_health(f"http://127.0.0.1:{gateway_port}")
        if not (t_ok and g_ok):
            pytest.fail(f"服务启动失败 template={t_ok} gateway={g_ok}")
        yield {
            "template": f"http://127.0.0.1:{template_port}",
            "gateway": f"http://127.0.0.1:{gateway_port}",
        }
    finally:
        for proc in (gateway, template):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()


def test_no_token_unauthorized(stack):
    resp = httpx.get(f"{stack['gateway']}/v1/users/x")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_create_user_via_gateway(stack):
    resp = httpx.post(
        f"{stack['gateway']}/v1/users",
        json={"email": "e2e@test.dev", "display_name": "E2E"},
        headers={**AUTH, "Idempotency-Key": "e2e-create-1", "traceparent": TRACE},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "e2e@test.dev"
    assert "x-request-id" in resp.headers  # 请求 ID 回写（定律5）


def test_idempotent_create_via_gateway(stack):
    headers = {**AUTH, "Idempotency-Key": "e2e-idem-1"}
    body = {"email": "idem@test.dev", "display_name": "Idem"}
    r1 = httpx.post(f"{stack['gateway']}/v1/users", json=body, headers=headers)
    r2 = httpx.post(f"{stack['gateway']}/v1/users", json=body, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json() == r2.json()


@pytest.fixture(scope="module")
def created_user(stack):
    resp = httpx.post(
        f"{stack['gateway']}/v1/users",
        json={"email": "e2e-flow@test.dev", "display_name": "Flow"},
        headers={**AUTH, "Idempotency-Key": "e2e-flow-1"},
    )
    assert resp.status_code == 201
    return {**stack, "uid": resp.json()["id"]}


def test_admin_read_via_gateway(created_user):
    resp = httpx.get(
        f"{created_user['gateway']}/v1/users/{created_user['uid']}", headers=AUTH
    )
    assert resp.status_code == 200


def test_direct_template_self_ok(created_user):
    resp = httpx.get(
        f"{created_user['template']}/v1/users/{created_user['uid']}",
        headers={"X-User-Id": created_user["uid"], "X-User-Roles": "user"},
    )
    assert resp.status_code == 200


def test_direct_template_other_forbidden(created_user):
    resp = httpx.get(
        f"{created_user['template']}/v1/users/{created_user['uid']}",
        headers={"X-User-Id": "someone-else", "X-User-Roles": "user"},
    )
    assert resp.status_code == 403