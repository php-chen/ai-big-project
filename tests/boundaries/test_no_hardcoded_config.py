"""边界扫描 · 方向一：禁止硬编码连接信息。

源码中不得出现生产连接串（postgres/mysql/redis/amqp/mongodb）；
测试内的 sqlite 内存串是允许的例外。
"""
from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import iter_source_files

FORBIDDEN_SCHEMES = (
    "postgresql+psycopg://",
    "postgres://",
    "postgresql://",
    "mysql://",
    "redis://",
    "amqp://",
    "mongodb://",
)


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_hardcoded_connection_strings(repo_root):
    violations: list[tuple[str, str]] = []
    for base_dir in (repo_root / "packages", repo_root / "services"):
        for py in iter_source_files(base_dir):
            for value in _string_constants(py):
                if value.lower().startswith(FORBIDDEN_SCHEMES):
                    violations.append((str(py.relative_to(repo_root)), value[:60]))
    assert not violations, (
        "源码禁止硬编码连接串（必须走环境变量，见 .env.example）：" + str(violations)
    )