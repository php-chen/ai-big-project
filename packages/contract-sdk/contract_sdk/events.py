"""事件信封（Event Envelope）：所有领域事件的统一线上包装。

这是“事件即契约”的载体：任何服务发布/订阅事件，都使用本信封。
信封本身是契约的一部分，禁止业务代码随意增删字段。
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TraceContext(BaseModel):
    """W3C traceparent 三段式上下文（定律5）。"""

    trace_id: str = Field(..., pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(..., pattern=r"^[0-9a-f]{16}$")
    trace_flags: str = Field(default="01", pattern=r"^[0-9a-f]{2}$")

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"


class EventEnvelope(BaseModel):
    """领域事件信封。event_name 必须带版本号，如 user.created.v1。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="事件唯一 ID（UUID 字符串）")
    event_name: str = Field(..., description="事件名（带版本，如 user.created.v1）")
    source: str = Field(..., description="产生事件的服务名")
    aggregate_type: str = Field(..., description="聚合类型，如 user")
    aggregate_id: str = Field(..., description="聚合根 ID")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict, description="事件消息体（对应 contracts/events/ 的 schema）")
    trace: TraceContext | None = Field(default=None, description="事件产生时的 trace 上下文（定律5）")


def new_event_id() -> str:
    import uuid

    return str(uuid.uuid4())