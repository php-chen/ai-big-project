"""契约测试 · 定律1：服务的 OpenAPI 实现必须覆盖契约（contract ⊆ implementation）。

- 契约中的每个 path+method 必须出现在服务的 OpenAPI 中；
- 契约声明的响应状态码必须被服务实现。
"""
from __future__ import annotations

import yaml
from app.config import ServiceSettings
from app.main import create_app


def _load_contract(repo_root, name: str) -> dict:
    path = repo_root / "contracts" / "http" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_template_implements_contract(repo_root):
    contract = _load_contract(repo_root, "template.openapi.yaml")
    app = create_app(
        settings=ServiceSettings(
            app_env="test",
            log_level="ERROR",
            database_url="sqlite+aiosqlite:///:memory:",
        )
    )
    spec = app.openapi()
    impl_paths = spec.get("paths", {})

    missing: list[str] = []
    for path, operations in contract["paths"].items():
        if path not in impl_paths:
            missing.append(f"{path} (路径未实现)")
            continue
        for method in operations:
            if method not in impl_paths[path]:
                missing.append(f"{method.upper()} {path} (方法未实现)")
                continue
            contract_statuses = set(operations[method].get("responses", {}).keys())
            impl_statuses = set(impl_paths[path][method].get("responses", {}).keys())
            uncovered = contract_statuses - impl_statuses
            if uncovered:
                missing.append(f"{method.upper()} {path} (契约状态码未实现: {sorted(uncovered)})")

    assert not missing, "服务实现未覆盖契约：\n" + "\n".join(missing)