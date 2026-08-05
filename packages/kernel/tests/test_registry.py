"""服务注册中心测试（动态扩容的实例清单）。"""
from __future__ import annotations

from kernel.registry import LocalServiceRegistry, build_registry


async def test_local_registry_register_list_deregister():
    registry = LocalServiceRegistry()
    await registry.register("service-template", "i-1", "http://a:1", ttl_seconds=30)
    await registry.register("service-template", "i-2", "http://b:1", ttl_seconds=30)
    urls = await registry.list("service-template")
    assert sorted(urls) == ["http://a:1", "http://b:1"]

    await registry.deregister("service-template", "i-1")
    assert await registry.list("service-template") == ["http://b:1"]
    await registry.close()


async def test_local_registry_ttl_expiry():
    registry = LocalServiceRegistry()
    await registry.register("svc", "i-1", "http://a:1", ttl_seconds=-1)  # 立即过期
    assert await registry.list("svc") == []
    await registry.close()


async def test_build_registry_without_redis_falls_back():
    registry = build_registry(None)
    assert isinstance(registry, LocalServiceRegistry)
    await registry.close()