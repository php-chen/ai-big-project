"""边界扫描 · 定律2：数据主权单向流。

1) 服务之间禁止相互 import（跨服务代码耦合 = 红线）；
2) 表归属唯一：任何表名不能同时出现在两个服务中；
3) 网关零数据访问：gateway_app 禁止 import sqlalchemy/内核 db。
"""
from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import SERVICE_PACKAGES


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _tablenames(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tables: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == "__tablename__"
                and isinstance(stmt.value, ast.Constant)
            ):
                tables.add(str(stmt.value.value))
    return tables


def test_no_cross_service_imports(repo_root):
    """服务之间禁止相互 import（红线段）。"""
    dirs = [(pkg, repo_root / "services" / svc / pkg) for pkg, svc in SERVICE_PACKAGES.items()]
    violations: list[tuple[str, str, str]] = []
    for pkg, base in dirs:
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            for mod in _imports(py):
                other = mod.split(".")[0]
                if other in SERVICE_PACKAGES and other != pkg:
                    violations.append((str(py.relative_to(repo_root)), mod, other))
    assert not violations, f"服务之间禁止相互 import：{violations}"


def test_table_ownership_is_unique(repo_root):
    """任何表名只能有一个 Owner 服务（定律2）。"""
    ownership: dict[str, set[str]] = {}
    for pkg, svc in SERVICE_PACKAGES.items():
        base = repo_root / "services" / svc / pkg
        if not base.exists():
            continue
        tables: set[str] = set()
        for py in base.rglob("*.py"):
            tables |= _tablenames(py)
        ownership[svc] = tables

    all_tables: dict[str, str] = {}
    duplicates: list[tuple[str, str, str]] = []
    for svc, tables in ownership.items():
        for t in tables:
            if t in all_tables:
                duplicates.append((t, all_tables[t], svc))
            else:
                all_tables[t] = svc
    assert not duplicates, f"表归属冲突（一个表多个 Owner）：{duplicates}"

    # 网关必须零表（零数据访问）
    assert not ownership.get("gateway", set()), "网关禁止拥有任何业务表"


def test_gateway_has_no_database_access(repo_root):
    """网关零数据访问：不 import sqlalchemy / 内核 db 基座。"""
    gw = repo_root / "services" / "gateway" / "gateway_app"
    violations = [
        (str(p.relative_to(repo_root)), mod)
        for p in gw.rglob("*.py")
        for mod in _imports(p)
        if mod.startswith(("sqlalchemy", "kernel.db", "kernel.outbox"))
    ]
    assert not violations, f"网关禁止访问数据库：{violations}"