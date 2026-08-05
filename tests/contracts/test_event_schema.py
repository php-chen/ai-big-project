"""契约测试 · 定律1+4：事件 payload 必须严格符合 contracts/events/*.json。

1) contract_sdk 镜像模型的输出符合契约 schema；
2) 服务实际登记到 outbox 的事件 payload 也符合契约 schema（跨层一致性）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from contract_sdk.schemas.user import UserCreatedPayload
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator
from sqlalchemy import select

from tests.conftest import REPO_ROOT

# 事件契约文件 -> 合法样例 payload 构造器（新增事件时在此登记）
SAMPLE_BUILDERS = {
    "user.created": lambda: UserCreatedPayload(
        user_id="4bf92f35-77b3-4da6-a3ce-929d0e0e4736",
        email="alice@example.com",
        display_name="Alice",
        vip_level=1,
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    ).model_dump(mode="json"),
}


@pytest.mark.parametrize(
    "contract_file",
    sorted((REPO_ROOT / "contracts" / "events").glob("*.json")),
    ids=lambda p: p.stem,
)
def test_contract_sdk_payload_conforms_to_schema(contract_file: Path):
    schema = json.loads(contract_file.read_text(encoding="utf-8"))
    event_key = contract_file.stem.removesuffix(".schema")  # user.created.schema -> user.created
    builder = SAMPLE_BUILDERS.get(event_key)
    assert builder is not None, f"缺少 {event_key} 的样例构造器，请在测试中登记"

    Draft202012Validator(schema).validate(builder())


async def test_staged_outbox_payload_conforms_to_schema():
    """服务实际写入 outbox 的事件，其 payload 必须符合契约（定律1+4）。"""
    from app.config import ServiceSettings
    from app.main import create_app
    from kernel.db import init_db
    from kernel.idempotency import InMemoryIdempotencyStore
    from kernel.outbox import OutboxMessage

    settings = ServiceSettings(
        app_env="test",
        log_level="ERROR",
        trust_proxy_headers=True,
        database_url="sqlite+aiosqlite:///:memory:",
    )
    app = create_app(settings=settings, idempotency_store=InMemoryIdempotencyStore())
    await init_db(app.state.engine)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/users",
                json={"email": "contract@test.dev", "display_name": "Contract"},
                headers={"X-User-Id": "u-1", "X-User-Roles": "user", "Idempotency-Key": "ct-1"},
            )
            assert resp.status_code == 201

        async with app.state.session_factory() as session:
            row = (await session.execute(select(OutboxMessage))).scalar_one()

        schema = json.loads(
            (REPO_ROOT / "contracts" / "events" / "user.created.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(row.payload)
    finally:
        await app.state.engine.dispose()