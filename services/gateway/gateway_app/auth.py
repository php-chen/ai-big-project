"""功能级鉴权（定律3）：网关只校验“能不能访问这个 URL”，不校验数据。"""
from __future__ import annotations

from kernel.context import Identity
from kernel.errors import UnauthorizedError

from .config import GatewaySettings


def verify_token(authorization: str | None, settings: GatewaySettings) -> Identity:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("缺少访问令牌")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.dev_token:
        raise UnauthorizedError("令牌无效")
    # 脚手架：生产应接入 JWT 校验（issuer/audience）或内部鉴权服务
    return Identity(user_id="dev-user", roles=("user", "admin"), tenant_id="dev-tenant")