"""users 表模型。

演进规则（方向三 Expand-Contract）：
- 新增字段必须带默认值（Python 侧 default + DB 侧 server_default）；
- 旧代码对新字段无感知。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from kernel.db import Base
from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    # 演进示例：新增字段必须带默认值（定律/方向三，迁移 0002）
    vip_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # server_default 用跨方言的 CURRENT_TIMESTAMP（sqlite/PG 均支持）
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("CURRENT_TIMESTAMP"),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )