"""HTTP DTO（镜像 contracts/http/template.openapi.yaml）。

注意：生产环境建议由 datamodel-code-generator 从 OpenAPI 自动生成，
本文件为手写示例，用于演示契约镜像的工作方式。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    display_name: str = Field(..., max_length=64)
    vip_level: int = 0


class UserOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    email: str
    display_name: str
    status: str = "active"
    vip_level: int = 0
    created_at: datetime