"""根级测试公共设施：仓库路径、源码遍历、契约加载、事件循环策略。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Windows + psycopg 异步：必须使用 SelectorEventLoop（Proactor 不受支持）。
# set_event_loop_policy 在 3.14 标记弃用，但 3.14.5 尚无 set_event_loop_factory，故沿用。
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

REPO_ROOT = Path(__file__).resolve().parents[1]

# 服务顶层包名（用于跨服务 import 边界扫描）
SERVICE_PACKAGES: dict[str, str] = {
    "app": "service-template",        # 服务模板的包名 -> 服务目录
    "gateway_app": "gateway",         # 网关的包名 -> 服务目录
}


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


def iter_source_files(base: Path) -> list[Path]:
    """遍历包源码 .py（排除缓存/egg-info/测试文件）。"""
    files: list[Path] = []
    for path in base.rglob("*.py"):
        parts = path.parts
        if any(p in {"__pycache__", ".egg-info", ".pytest_cache", ".ruff_cache"} for p in parts):
            continue
        if "tests" in parts or path.name.startswith("test_"):
            continue
        files.append(path)
    return files


def iter_contract_files(repo_root: Path, subdir: str) -> list[Path]:
    d = repo_root / "contracts" / subdir
    return sorted(d.glob("*")) if d.exists() else []