"""用户领域服务。

定律2：只操作 users 表（本服务拥有）；
定律4：创建用户在本地事务内同时写入 outbox，提交后由 relay 异步发布 user.created.v1；
读写分离：写操作走主库（write_factory），查询走从库（read_factory）；
状态码：业务错误抛 AppError + 注册表业务码（前端据此分支）。
"""
from __future__ import annotations

from datetime import UTC, datetime

from contract_sdk.events import EventEnvelope, new_event_id
from contract_sdk.schemas.user import UserCreatedPayload
from kernel.db import DatabaseRouter
from kernel.errors import ConflictError, NotFoundError
from kernel.events import envelope_trace_from_context
from kernel.outbox import stage_outbox
from sqlalchemy import select

from ..error_codes import EMAIL_ALREADY_EXISTS, USER_NOT_FOUND
from ..models.user import User


class UserService:
    def __init__(self, db: DatabaseRouter) -> None:
        self._db = db

    async def create_user(self, email: str, display_name: str, vip_level: int = 0) -> User:
        # 写会话：绑定主库（写 + 读己之写保证）
        async with self._db.write_factory() as session:
            exists = await session.execute(select(User.id).where(User.email == email))
            if exists.scalar_one_or_none():
                raise ConflictError(code=EMAIL_ALREADY_EXISTS.code, message="邮箱已存在")

            user = User(email=email, display_name=display_name, vip_level=vip_level)
            session.add(user)
            await session.flush()

            # 本地事务 + Outbox（定律4）：与业务写操作同一事务
            envelope = EventEnvelope(
                event_id=new_event_id(),
                event_name="user.created.v1",
                source="service-template",
                aggregate_type="user",
                aggregate_id=user.id,
                occurred_at=datetime.now(UTC),
                payload=UserCreatedPayload(
                    user_id=user.id,
                    email=user.email,
                    display_name=user.display_name,
                    vip_level=user.vip_level,
                    created_at=user.created_at,
                ).model_dump(mode="json"),
                trace=envelope_trace_from_context(),
            )
            stage_outbox(session, envelope)

            await session.commit()
            await session.refresh(user)
            return user

    async def get_user(self, user_id: str) -> User:
        # 读会话：绑定从库（read replica）
        async with self._db.read_factory() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise NotFoundError(code=USER_NOT_FOUND.code, message="用户不存在")
            return user

    async def list_users(self, limit: int = 100) -> list[User]:
        # 读会话：绑定从库
        async with self._db.read_factory() as session:
            rows = (
                (await session.execute(select(User).order_by(User.created_at.desc()).limit(limit)))
                .scalars()
                .all()
            )
            return list(rows)