"""异步数据库基座（SQLAlchemy 2.0 async + psycopg）· 读写分离 + 读副本负载均衡。

路由策略（见 docs/standards/database.md）：
- 写会话（write_factory）绑定主库：写 + 读己之写天然保证；
- 读会话（read_factory）在多个从库之间轮询（round-robin），未配置副本时复用主库；
- 未配置 REPLICA_DATABASE_URL(S) 时从库自动降级（全部走主库）。

说明：SQLAlchemy 2.0 async 下语句级 get_bind 跨引擎切换会触发
AsyncContextNotStarted（已知限制），因此采用“写/读双工厂”路由。

演进规则（方向三）：新增字段必须带默认值；生产迁移用 Alembic（create_all 仅限开发/测试）。
"""
from __future__ import annotations

import itertools
import logging
import time
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """领域模型基类。"""


def build_engine(database_url: str, echo: bool = False) -> AsyncEngine:
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool  # 测试用：内存库跨连接共享
    return create_async_engine(database_url, echo=echo, **kwargs)


def build_engines(database_url: str, replica_database_url: str | None = None, echo: bool = False):
    """构建主/从双引擎；无副本时 read_engine 为 None。"""
    write_engine = build_engine(database_url, echo=echo)
    read_engine = build_engine(replica_database_url, echo=echo) if replica_database_url else None
    return write_engine, read_engine


async def _engine_ok(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - 健康检查有意捕获所有异常
        return False


class DatabaseRouter:
    """读写分离路由器：写会话（主库）与读会话（多从库轮询）。

    用法：
        router = build_database_router(database_url, replica_database_urls=[...])
        async with router.write_factory() as s: ...   # 写（主库）
        async with router.read_factory() as s: ...    # 读（轮询从库）
    """

    def __init__(
        self,
        write_engine: AsyncEngine,
        read_engines: list[AsyncEngine] | None = None,
    ) -> None:
        self.write_engine = write_engine
        self.read_engines = read_engines if read_engines else [write_engine]
        self.write_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.write_engine, expire_on_commit=False
        )
        self._read_factories = [
            async_sessionmaker(engine, expire_on_commit=False) for engine in self.read_engines
        ]
        self._rr = itertools.cycle(range(len(self._read_factories)))

    @property
    def has_replica(self) -> bool:
        return len(self.read_engines) > 1 or self.read_engines[0] is not self.write_engine

    @property
    def read_factory(self) -> async_sessionmaker[AsyncSession]:
        """读会话工厂：在多个从库之间轮询（负载均衡）。"""
        return self._read_factories[next(self._rr)]

    async def check_write(self) -> bool:
        """健康检查：主库连通性（db_write）。"""
        return await _engine_ok(self.write_engine)

    async def check_read(self) -> bool:
        """健康检查：至少一个从库可用（db_read）。"""
        for engine in self.read_engines:
            if await _engine_ok(engine):
                return True
        return False

    async def dispose(self) -> None:
        await self.write_engine.dispose()
        seen: set[int] = set()
        for engine in self.read_engines:
            if id(engine) not in seen:
                seen.add(id(engine))
                await engine.dispose()


def build_database_router(
    database_url: str,
    replica_database_url: str | None = None,
    replica_database_urls: list[str] | None = None,
    echo: bool = False,
) -> DatabaseRouter:
    """构建读写分离路由器（支持多个读副本，无副本时自动降级主库）。"""
    write_engine = build_engine(database_url, echo=echo)
    read_urls: list[str] = []
    if replica_database_urls:
        read_urls.extend(u for u in replica_database_urls if u)
    elif replica_database_url:
        read_urls.append(replica_database_url)
    read_engines = [build_engine(u, echo=echo) for u in read_urls] if read_urls else None
    return DatabaseRouter(write_engine, read_engines)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """单引擎会话工厂（无读写分离时的简单模式/测试）。"""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(engine: AsyncEngine) -> None:
    """建表（仅开发/测试；生产必须使用 Alembic 迁移）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def make_db_check(session_factory: async_sessionmaker[AsyncSession]):
    """健康检查用：数据库连通性探测（主库；/health/ready 使用）。"""

    async def check() -> bool:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - 健康检查有意捕获所有异常
            return False

    return check


def make_engine_check(engine: AsyncEngine):
    """健康检查用：指定引擎连通性探测。"""

    async def check() -> bool:
        return await _engine_ok(engine)

    return check


def enable_slow_query_logging(
    engine: AsyncEngine,
    threshold_ms: int = 200,
    engine_role: str = "write",
) -> None:
    """记录慢查询（定律5）：SQL + 耗时，并自动附带 request_id/trace_id。

    threshold_ms <= 0 表示关闭。只对指定引擎生效（建议主库开启）。
    """
    if threshold_ms <= 0:
        return
    slow_logger = logging.getLogger("kernel.db.slow")
    start_times: dict = {}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
        start_times[cursor] = time.perf_counter()

    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
        started = start_times.pop(cursor, None)
        if started is None:
            return
        duration_ms = (time.perf_counter() - started) * 1000
        if duration_ms >= threshold_ms:
            slow_logger.warning(
                "slow query",
                extra={
                    "ctx": {
                        "duration_ms": round(duration_ms, 1),
                        "sql": str(statement)[:500],
                        "engine": engine_role,
                    }
                },
            )

    from sqlalchemy import event

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)


async def get_session_dependency(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖工厂：每请求一个会话。"""
    async with session_factory() as session:
        yield session