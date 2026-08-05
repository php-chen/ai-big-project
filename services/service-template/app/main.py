"""服务模板入口：装配内核基座 + 本服务路由/依赖。

启动：uvicorn app.main:app --host 0.0.0.0 --port 8100
"""
from __future__ import annotations

import asyncio
import socket
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from kernel.app import create_app as kernel_create_app
from kernel.db import build_database_router, enable_slow_query_logging, init_db
from kernel.events import build_event_bus
from kernel.idempotency import InMemoryIdempotencyStore, build_idempotency_store
from kernel.outbox import OutboxRelay
from kernel.registry import build_registry, run_heartbeat

from .api.routes import router
from .config import ServiceSettings
from .domain.user_service import UserService


def _lifespan(
    write_engine,
    session_factory,
    bus,
    database_url: str,
    app_env: str,
    use_skip_locked: bool,
    registry,
    service_name: str,
    instance_id: str,
    instance_url: str,
    registry_ttl: int,
):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 开发便利：sqlite 开发环境自动建表；生产必须走 Alembic（方向三）
        if app_env == "development" and database_url.startswith("sqlite"):
            await init_db(write_engine)

        # 动态扩容：向注册中心登记本实例 + 心跳（网关据此动态发现副本）
        heartbeat = asyncio.create_task(
            run_heartbeat(registry, service_name, instance_id, instance_url, registry_ttl)
        )

        # 定律4：Outbox relay 后台投递（写会话 = 主库；skip_locked 保证多副本单写者）
        relay = OutboxRelay(session_factory, bus, use_skip_locked=use_skip_locked, service_name=service_name)
        task = asyncio.create_task(relay.run_forever())
        try:
            yield
        finally:
            task.cancel()
            heartbeat.cancel()
            try:
                await asyncio.gather(task, heartbeat, return_exceptions=True)
            finally:
                await registry.deregister(service_name, instance_id)
                await registry.close()

    return lifespan


def create_app(
    settings: ServiceSettings | None = None,
    idempotency_store=None,
) -> FastAPI:
    settings = settings or ServiceSettings()
    database_url = settings.database_url or "sqlite+aiosqlite:///:memory:"
    # 读写分离：主库写 + 多从库读轮询（未配置副本时自动降级）
    db = build_database_router(
        database_url,
        replica_database_url=settings.replica_database_url,
        replica_database_urls=settings.replica_database_url_list,
    )

    # 慢查询日志（定律5）：SQL + 耗时 + trace_id，主/从分别开启
    if settings.log_slow_query_ms > 0:
        enable_slow_query_logging(db.write_engine, settings.log_slow_query_ms, "write")
        for engine in db.read_engines:
            enable_slow_query_logging(engine, settings.log_slow_query_ms, "read")

    # 定律4：事件总线——配置 AMQP_URL 用 RabbitMQ（生产），否则本地总线（开发/测试）
    bus = build_event_bus(settings.amqp_url)

    if idempotency_store is None:
        idempotency_store = (
            build_idempotency_store(settings.redis_url, settings.idempotency_ttl_seconds)
            if settings.redis_url
            else InMemoryIdempotencyStore()
        )

    # 服务注册（动态扩容）：本实例地址默认 http://<service>:<port>
    registry = build_registry(settings.registry_url)
    instance_id = f"{settings.service_name}-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    instance_url = settings.instance_url or f"http://{settings.service_name}:{settings.port}"

    # SQLite 不支持 FOR UPDATE SKIP LOCKED（仅开发）；PG 生产开启
    use_skip_locked = not database_url.startswith("sqlite")
    app = kernel_create_app(
        settings=settings,
        title="Service Template API",
        routers=[router],
        lifespan=_lifespan(
            db.write_engine,
            db.write_factory,
            bus,
            database_url,
            settings.app_env,
            use_skip_locked,
            registry,
            settings.service_name,
            instance_id,
            instance_url,
            settings.service_registry_ttl_seconds,
        ),
        health_checks={"db_write": db.check_write, "db_read": db.check_read},
        idempotency_store=idempotency_store,
    )
    app.state.db = db
    app.state.write_engine = db.write_engine
    app.state.read_engine = db.read_engines[0] if db.read_engines else db.write_engine
    app.state.engine = db.write_engine  # 兼容：init_db / 测试
    app.state.session_factory = db.write_factory
    app.state.event_bus = bus
    app.state.user_service = UserService(db)
    return app


app = create_app()