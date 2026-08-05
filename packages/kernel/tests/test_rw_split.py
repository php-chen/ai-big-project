"""读写分离 + 读副本负载均衡测试：
- 读会话（read_factory）=> 从库；多从库轮询；
- 写会话（write_factory）=> 主库，且会话内读己之写天然走主库；
- 无副本时自动降级主库。
用 before_cursor_execute 计数验证 SQL 实际执行在哪个引擎。
"""
from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, event, select
from sqlalchemy.orm import Mapped, mapped_column

from kernel.db import (
    Base,
    DatabaseRouter,
    build_database_router,
    build_engine,
    init_db,
)


class RwItem(Base):
    __tablename__ = "rw_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))


@pytest.fixture
async def router():
    db = build_database_router(
        "sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite:///:memory:"
    )
    await init_db(db.write_engine)
    for engine in db.read_engines:
        await init_db(engine)
    counts = {"write": 0, "read": 0}

    def count_write(*_args, **_kw):
        counts["write"] += 1

    def count_read(*_args, **_kw):
        counts["read"] += 1

    event.listen(db.write_engine.sync_engine, "before_cursor_execute", count_write)
    event.listen(db.read_engines[0].sync_engine, "before_cursor_execute", count_read)
    try:
        yield db, counts
    finally:
        event.remove(db.write_engine.sync_engine, "before_cursor_execute", count_write)
        event.remove(db.read_engines[0].sync_engine, "before_cursor_execute", count_read)
        await db.dispose()


async def test_read_factory_uses_replica(router):
    db, counts = router
    assert db.has_replica is True
    async with db.read_factory() as session:
        await session.execute(select(RwItem))
    assert counts["read"] >= 1
    assert counts["write"] == 0


async def test_write_factory_uses_primary(router):
    db, counts = router
    async with db.write_factory() as session:
        session.add(RwItem(name="a"))
        await session.commit()
    assert counts["write"] >= 1
    assert counts["read"] == 0


async def test_write_then_read_in_write_session_uses_primary(router):
    """写会话内读己之写天然在主库（不会读到滞后副本）。"""
    db, counts = router
    async with db.write_factory() as session:
        session.add(RwItem(name="a"))
        await session.flush()
        await session.execute(select(RwItem))
    assert counts["write"] >= 1
    assert counts["read"] == 0


async def test_no_replica_falls_back_to_primary():
    db = build_database_router("sqlite+aiosqlite:///:memory:", None)
    await init_db(db.write_engine)
    assert db.has_replica is False
    counts = {"write": 0, "read": 0}

    def count_write(*_args, **_kw):
        counts["write"] += 1

    event.listen(db.write_engine.sync_engine, "before_cursor_execute", count_write)
    try:
        async with db.read_factory() as session:
            await session.execute(select(RwItem))
    finally:
        event.remove(db.write_engine.sync_engine, "before_cursor_execute", count_write)
        await db.dispose()
    assert counts["write"] >= 1  # 无副本时读也走主库


async def test_health_checks(router):
    db, _counts = router
    assert await db.check_write() is True
    assert await db.check_read() is True


async def test_read_round_robin_across_replicas():
    """读副本负载均衡：多个从库之间轮询。"""
    write_engine = build_engine("sqlite+aiosqlite:///:memory:")
    r1 = build_engine("sqlite+aiosqlite:///:memory:")
    r2 = build_engine("sqlite+aiosqlite:///:memory:")
    for engine in (write_engine, r1, r2):
        await init_db(engine)

    db = DatabaseRouter(write_engine, [r1, r2])
    counts = {"r1": 0, "r2": 0}

    def count_r1(*_a, **_k):
        counts["r1"] += 1

    def count_r2(*_a, **_k):
        counts["r2"] += 1

    event.listen(r1.sync_engine, "before_cursor_execute", count_r1)
    event.listen(r2.sync_engine, "before_cursor_execute", count_r2)
    try:
        for _ in range(4):
            async with db.read_factory() as session:
                await session.execute(select(RwItem))
    finally:
        event.remove(r1.sync_engine, "before_cursor_execute", count_r1)
        event.remove(r2.sync_engine, "before_cursor_execute", count_r2)
        await db.dispose()
        await write_engine.dispose()

    assert counts["r1"] == 2, f"r1 应被轮询 2 次，实际 {counts['r1']}"
    assert counts["r2"] == 2, f"r2 应被轮询 2 次，实际 {counts['r2']}"