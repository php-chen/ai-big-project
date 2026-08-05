"""Outbox 测试（定律4：本地事务 + Outbox，提交后投递；事件契约走信封）。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from contract_sdk.events import EventEnvelope
from pydantic import ValidationError
from sqlalchemy import select

from kernel.db import build_engine, build_session_factory, init_db
from kernel.events import LocalEventBus
from kernel.outbox import OutboxMessage, OutboxRelay, stage_outbox


@pytest.fixture
async def session_factory():
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    yield build_session_factory(engine)
    await engine.dispose()


def make_envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id=str(uuid.uuid4()),
        event_name="user.created.v1",
        source="kernel-test",
        aggregate_type="user",
        aggregate_id=str(uuid.uuid4()),
        occurred_at=datetime.now(UTC),
        payload={"user_id": "u-1", "email": "a@b.c", "display_name": "A"},
    )


async def test_stage_and_relay(session_factory):
    bus = LocalEventBus()
    received: list[EventEnvelope] = []

    async def handler(envelope: EventEnvelope) -> None:
        received.append(envelope)

    bus.subscribe("user.created.v1", handler)
    relay = OutboxRelay(session_factory, bus, poll_interval=0.05, use_skip_locked=False)

    envelope = make_envelope()
    async with session_factory() as session:
        stage_outbox(session, envelope)
        await session.commit()

    delivered = await relay.run_once()
    assert delivered == 1
    assert len(received) == 1
    assert received[0].event_name == "user.created.v1"
    assert received[0].payload["user_id"] == "u-1"

    async with session_factory() as session:
        row = (await session.execute(select(OutboxMessage))).scalar_one()
        assert row.status == "sent"
        assert row.sent_at is not None


async def test_event_envelope_forbids_extra_fields():
    with pytest.raises(ValidationError):
        EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_name="user.created.v1",
            source="t",
            aggregate_type="user",
            aggregate_id="u",
            payload={},
            invented_field="x",  # type: ignore[call-arg]
        )