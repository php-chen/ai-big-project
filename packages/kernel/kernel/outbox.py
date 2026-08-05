"""事务发件箱（Outbox，定律4 的落地核心）。

流程：业务本地事务内同时写入 outbox_messages -> 提交后由 OutboxRelay 异步投递。
- 禁止在事务提交前直接发 MQ；
- 投递失败指数退避重试，超过最大次数标记 FAILED（可人工/死信处理）；
- 暴露 outbox_pending_total 队列深度指标（资源监控）。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from contract_sdk.events import EventEnvelope
from prometheus_client import Gauge
from sqlalchemy import JSON, DateTime, Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .events import EventPublisher

logger = logging.getLogger(__name__)

OUTBOX_PENDING = Gauge("outbox_pending_total", "待投递的 outbox 消息数（队列深度）", ["service"])

MAX_ATTEMPTS = 8
BASE_BACKOFF_SECONDS = 2.0


class OutboxStatus:
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_name: Mapped[str] = mapped_column(String(128), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default=OutboxStatus.PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def stage_outbox(session: Any, envelope: EventEnvelope) -> OutboxMessage:
    """在同一业务事务内登记待投递事件（必须与业务写操作同一事务）。"""
    message = OutboxMessage(
        event_name=envelope.event_name,
        aggregate_type=envelope.aggregate_type,
        aggregate_id=envelope.aggregate_id,
        payload=envelope.payload,
        headers={"trace": envelope.trace.model_dump() if envelope.trace else None},
    )
    session.add(message)
    return message


class OutboxRelay:
    """后台投递器：轮询 pending 消息 -> 发布到事件总线 -> 标记 sent。"""

    def __init__(
        self,
        session_factory: Any,
        publisher: EventPublisher,
        poll_interval: float = 2.0,
        batch_size: int = 100,
        use_skip_locked: bool = True,
        service_name: str = "service",
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._use_skip_locked = use_skip_locked
        self._service_name = service_name

    async def run_once(self) -> int:
        """处理一批到期消息，返回投递成功的数量。"""
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            stmt = (
                select(OutboxMessage)
                .where(
                    OutboxMessage.status == OutboxStatus.PENDING,
                    (OutboxMessage.next_attempt_at.is_(None))
                    | (OutboxMessage.next_attempt_at <= now),
                )
                .order_by(OutboxMessage.created_at.asc())
                .limit(self._batch_size)
            )
            # 多副本单写者：行锁 + 跳过已锁行，避免重复投递（横向扩容安全）
            if self._use_skip_locked:
                stmt = stmt.with_for_update(skip_locked=True)
            rows = (
                (await session.execute(stmt))
                .scalars()
                .all()
            )
            delivered = 0
            for row in rows:
                envelope = self._to_envelope(row)
                try:
                    await self._publisher.publish(envelope)
                    row.status = OutboxStatus.SENT
                    row.sent_at = datetime.now(UTC)
                    row.attempts += 1
                    delivered += 1
                except Exception:  # noqa: BLE001 - 投递失败走重试
                    row.attempts += 1
                    if row.attempts >= MAX_ATTEMPTS:
                        row.status = OutboxStatus.FAILED
                        logger.error("Outbox 消息投递失败已达上限: %s/%s", row.event_name, row.id)
                    else:
                        row.next_attempt_at = now + timedelta(
                            seconds=BASE_BACKOFF_SECONDS * (2 ** min(row.attempts, 6))
                        )
                        logger.warning("Outbox 投递失败将重试: %s/%s attempts=%s", row.event_name, row.id, row.attempts)

            # 队列深度指标（资源监控：Outbox 积压量）
            pending_count = (
                await session.execute(
                    select(func.count())
                    .select_from(OutboxMessage)
                    .where(OutboxMessage.status == OutboxStatus.PENDING)
                )
            ).scalar_one()
            OUTBOX_PENDING.labels(self._service_name).set(pending_count or 0)

            await session.commit()
            return delivered

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Outbox relay 批次处理异常")
            await asyncio.sleep(self._poll_interval)

    @staticmethod
    def _to_envelope(row: OutboxMessage) -> EventEnvelope:
        trace_data = (row.headers or {}).get("trace")
        trace = None
        if isinstance(trace_data, dict):
            from contract_sdk.events import TraceContext

            try:
                trace = TraceContext.model_validate(trace_data)
            except Exception:  # noqa: BLE001 - 容错解析 trace
                trace = None
        return EventEnvelope(
            event_id=row.id,
            event_name=row.event_name,
            source="",  # relay 不修改事件源；由业务 staging 时记录到 headers
            aggregate_type=row.aggregate_type,
            aggregate_id=row.aggregate_id,
            occurred_at=row.created_at,
            payload=row.payload,
            trace=trace,
        )