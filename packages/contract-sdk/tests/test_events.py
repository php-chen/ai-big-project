"""契约 SDK 测试：事件信封、traceparent、schema 演进兼容。"""
from __future__ import annotations

from datetime import UTC, datetime

from contract_sdk.events import EventEnvelope, TraceContext, new_event_id
from contract_sdk.schemas.user import UserCreatedPayload


def test_envelope_roundtrip():
    env = EventEnvelope(
        event_id=new_event_id(),
        event_name="user.created.v1",
        source="test",
        aggregate_type="user",
        aggregate_id="u-1",
        payload={"user_id": "u-1"},
    )
    restored = EventEnvelope.model_validate_json(env.model_dump_json())
    assert restored.event_name == "user.created.v1"
    assert restored.aggregate_id == "u-1"


def test_traceparent_format():
    tc = TraceContext(trace_id="4bf92f3577b34da6a3ce929d0e0e4736", span_id="00f067aa0ba902b7")
    assert tc.traceparent == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_user_payload_ignores_unknown_fields():
    """方向三：旧代码对新字段无感知（extra=ignore）。"""
    payload = UserCreatedPayload(
        user_id="u-1",
        email="a@b.c",
        display_name="A",
        created_at=datetime(2026, 8, 4, tzinfo=UTC),
        some_future_field=123,  # type: ignore[call-arg]
    )
    assert payload.vip_level == 0