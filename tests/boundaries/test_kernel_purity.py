"""边界扫描 · 定律/方向二：内核零业务属性。

内核（packages/kernel/kernel）禁止 import 任何服务的顶层包（app / gateway_app / services），
只允许依赖契约层（contract_sdk）与基础设施包。
"""
from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import SERVICE_PACKAGES

FORBIDDEN_TOP = set(SERVICE_PACKAGES) | {"services"}


def _module_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_kernel_never_imports_services(repo_root):
    kernel_dir = repo_root / "packages" / "kernel" / "kernel"
    violations = [
        (str(p.relative_to(repo_root)), mod)
        for p in kernel_dir.rglob("*.py")
        for mod in _module_names(p)
        if mod.split(".")[0] in FORBIDDEN_TOP
    ]
    assert not violations, f"内核禁止 import 服务/业务包（违反洋葱边界）：{violations}"


def test_kernel_supports_contract_sdk_dependency(repo_root):
    """内核可以依赖契约层（共享词汇），这是洋葱模型的合法方向。"""
    kernel_dir = repo_root / "packages" / "kernel" / "kernel"
    uses_contracts = any(
        mod.split(".")[0] == "contract_sdk"
        for p in kernel_dir.rglob("*.py")
        for mod in _module_names(p)
    )
    assert uses_contracts, "内核应通过 contract_sdk 使用事件信封（EventEnvelope）"