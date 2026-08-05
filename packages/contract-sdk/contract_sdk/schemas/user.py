"""用户域 schema（镜像 contracts/events/user.created.schema.json）。

演进规则：新增字段必须带默认值；删除/改名 = 破坏性变更，必须升版本。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreatedPayload(BaseModel):
    """user.created.v1 事件消息体。"""

    model_config = ConfigDict(extra="ignore")  # 方向三：旧代码对新字段无感知

    user_id: str
    email: str
    display_name: str = Field(..., max_length=64)
    vip_level: int = 0  # 演进示例：新增字段必须带默认值
    created_at: datetime