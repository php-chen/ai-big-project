"""集成测试 · 定律4：真实中间件（PostgreSQL + Redis + RabbitMQ）下的完整链路。

- 本地事务 + Outbox：创建用户时业务与 outbox 同事务落库（PostgreSQL）；
- OutboxRelay 投递到 RabbitMQ；EventConsumer 幂等消费；
- 事件 payload 符合 contracts/events/user.created.schema.json（定律1）。

需要 Docker（testcontainers 自动拉起容器）；不可用时自动跳过：pytest -m integration
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from kernel.db import DatabaseRouter, build_engine, init_db
from kernel.errors import ConflictError
from kernel.events import EventConsumer, RabbitEventBus
from kernel.idempotency import RedisIdempotencyStore
from kernel.outbox import OutboxRelay

REPO_ROOT = Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=15, check=False
        )
        return result.returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _docker_available(), reason="Docker 不可用，跳过集成测试"),
]


@pytest.fixture(scope="module")
def middleware():
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.rabbitmq import RabbitMqContainer
    from testcontainers.community.redis import RedisContainer

    postgres = PostgresContainer("postgres:16-alpine")
    redis = RedisContainer("redis:7-alpine")
    rabbit = RabbitMqContainer("rabbitmq:3-management-alpine")
    postgres.start()
    redis.start()
    rabbit.start()
    try:
        db_url = postgres.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+psycopg://"
        )
        amqp_url = (
            f"amqp://guest:guest@{rabbit.get_container_host_ip()}:"
            f"{rabbit.get_exposed_port(5672)}/"
        )
        yield {
            "database_url": db_url,
            "redis_url": f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
            "amqp_url": amqp_url,
        }
    finally:
        rabbit.stop()
        redis.stop()
        postgres.stop()


def _make_router(middleware) -> tuple[object, DatabaseRouter]:
    engine = build_engine(middleware["database_url"])
    return engine, DatabaseRouter(engine)


async def test_outbox_rabbit_full_flow(middleware):
    """创建用户 -> outbox 落库 -> relay 投递 RabbitMQ -> 消费端收到且符合契约。"""
    from app.domain.user_service import UserService

    _engine, db = _make_router(middleware)
    await init_db(db.write_engine)

    bus = RabbitEventBus(middleware["amqp_url"])
    received: list = []

    async def handler(envelope) -> None:
        received.append(envelope)

    consumer = EventConsumer(bus)
    await consumer.subscribe("user.created.v1", handler)

    try:
        service = UserService(db)
        user = await service.create_user("flow@test.dev", "Flow")

        relay = OutboxRelay(db.write_factory, bus)
        delivered = await relay.run_once()
        assert delivered == 1

        for _ in range(20):
            if received:
                break
            await asyncio.sleep(0.5)
        assert len(received) == 1, "RabbitMQ 未在预期时间内投递事件"
        assert received[0].event_name == "user.created.v1"
        assert received[0].payload["user_id"] == user.id

        schema = json.loads(
            (REPO_ROOT / "contracts" / "events" / "user.created.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(received[0].payload)
    finally:
        await bus.close()
        await db.dispose()


async def test_duplicate_email_conflict_on_real_db(middleware):
    from app.domain.user_service import UserService

    _engine, db = _make_router(middleware)
    await init_db(db.write_engine)
    try:
        service = UserService(db)
        await service.create_user("dup@test.dev", "Dup")
        with pytest.raises(ConflictError):
            await service.create_user("dup@test.dev", "Dup")
    finally:
        await db.dispose()


async def test_redis_idempotency_store(middleware):
    store = RedisIdempotencyStore(middleware["redis_url"])
    try:
        assert await store.acquire("k-1", 60) is True
        assert await store.acquire("k-1", 60) is False
        await store.put("k-1", "done", 60)
        assert await store.get("k-1") == "done"
    finally:
        await store.close()