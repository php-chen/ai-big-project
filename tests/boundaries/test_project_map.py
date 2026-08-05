"""项目地图校验（防漂移）：project-map.yaml 必须与仓库实际结构一致。

新增/修改服务、包、契约、事件、表归属时，必须同步更新 project-map.yaml，
否则本测试失败（地图 = 全局导航，漂移会让所有人迷路）。
"""
from __future__ import annotations

from pathlib import Path

import yaml

REQUIRED_TOP = {"project", "packages", "services", "middleware", "contracts", "events"}


def _load_map(repo_root: Path) -> dict:
    path = repo_root / "project-map.yaml"
    assert path.is_file(), "缺少 project-map.yaml（项目地图）"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "project-map.yaml 必须是 YAML 映射"
    return data


def test_map_structure(repo_root):
    data = _load_map(repo_root)
    assert set(data) >= REQUIRED_TOP, f"地图缺少必需顶层段: {REQUIRED_TOP - set(data)}"
    assert data["version"], "地图缺少 version"


def test_package_paths_exist(repo_root):
    data = _load_map(repo_root)
    for name, pkg in data["packages"].items():
        assert pkg.get("path"), f"包 {name} 缺少 path"
        assert (repo_root / pkg["path"]).is_dir(), f"包路径不存在: {pkg['path']}"


def test_service_paths_and_ports(repo_root):
    data = _load_map(repo_root)
    for name, svc in data["services"].items():
        assert svc.get("path"), f"服务 {name} 缺少 path"
        assert (repo_root / svc["path"]).is_dir(), f"服务路径不存在: {svc['path']}"
        assert svc.get("port", 0) > 0, f"服务 {name} 缺少有效端口"


def test_contract_files_exist(repo_root):
    data = _load_map(repo_root)
    files = data["contracts"].get("http", []) + data["contracts"].get("events", [])
    assert files, "地图 contracts 为空"
    for contract in files:
        assert (repo_root / contract).is_file(), f"契约文件不存在: {contract}"


def test_events_reference_existing_schemas_and_publishers(repo_root):
    data = _load_map(repo_root)
    services = data["services"]
    for event in data["events"]:
        assert event.get("name"), "事件缺少 name"
        assert (repo_root / event["schema"]).is_file(), f"事件 schema 不存在: {event['schema']}"
        assert event["publisher"] in services, f"事件发布者未登记: {event['publisher']}"
        for consumer in event.get("consumers", []):
            assert consumer in services, f"事件消费者未登记: {consumer}"


def test_table_ownership_unique_in_map(repo_root):
    data = _load_map(repo_root)
    owners: dict[str, str] = {}
    for name, svc in data["services"].items():
        for table in svc.get("owns_tables", []):
            assert table not in owners, f"表 {table} 归属冲突（{owners[table]} 与 {name}）"
            owners[table] = name


def test_deployment_files_exist(repo_root):
    data = _load_map(repo_root)
    deploy = data.get("deployment", {})
    for path in deploy.get("compose", {}).values():
        assert (repo_root / path).is_file(), f"编排文件不存在: {path}"
    cd = deploy.get("cd", {})
    assert (repo_root / cd["workflow"]).is_file(), f"CD 工作流不存在: {cd['workflow']}"