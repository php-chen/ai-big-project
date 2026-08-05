"""鉴权基座（定律3：二维防线 + 默认拒绝）。

- 功能级：网关做（本内核不重复实现）；
- 数据级：业务服务使用本模块的依赖/帮助函数，**默认拒绝**，
  按属主 / 租户 / 角色显式授权。
"""
from __future__ import annotations

from fastapi import Depends

from .context import Identity, get_identity
from .errors import ForbiddenError, UnauthorizedError


def get_current_identity() -> Identity:
    """要求存在可信身份（未认证 -> 401）。默认拒绝：无身份头即视为未认证。"""
    identity = get_identity()
    if identity is None or identity.user_id is None:
        raise UnauthorizedError("未认证：缺少可信身份")
    return identity


def require_roles(*roles: str):
    """角色依赖工厂：至少拥有其中一个角色才放行（否则 403）。"""

    def dependency(identity: Identity = Depends(get_current_identity)) -> Identity:
        if roles and not (set(identity.roles) & set(roles)):
            raise ForbiddenError(f"需要角色: {', '.join(roles)}")
        return identity

    return dependency


def ensure_owner(owner_id: str, identity: Identity | None = None) -> None:
    """数据级授权：资源属主或 admin 才可访问（否则 403）。"""
    identity = identity or get_identity()
    if identity is None or identity.user_id is None:
        raise UnauthorizedError("未认证：缺少可信身份")
    if identity.user_id != owner_id and "admin" not in identity.roles:
        raise ForbiddenError("无权访问该资源")


def ensure_tenant(identity: Identity | None = None) -> str:
    """数据级授权：多租户场景必须带租户上下文（否则 403）。"""
    identity = identity or get_identity()
    if identity is None or not identity.tenant_id:
        raise ForbiddenError("缺少租户上下文")
    return identity.tenant_id