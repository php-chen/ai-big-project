"""用户路由。

定律3：业务只做数据级授权（默认拒绝），功能级权限由网关负责；
      本服务不重复校验菜单/URL，只校验“能否看到这条数据”。
状态码：错误统一抛 AppError + 注册表业务码（RFC 9457）。
"""
from __future__ import annotations

from contract_sdk.schemas.http import UserCreate, UserOut
from fastapi import APIRouter, Depends, Request
from kernel.auth import ensure_owner, require_roles

from ...domain.user_service import UserService

router = APIRouter(prefix="/v1/users", tags=["users"])


def _user_service(request: Request) -> UserService:
    return request.app.state.user_service


def _to_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        vip_level=user.vip_level,
        created_at=user.created_at,
    )


@router.post(
    "",
    status_code=201,
    response_model=UserOut,
    responses={
        401: {"description": "未认证（默认拒绝）"},
        403: {"description": "角色无权访问"},
        409: {"description": "邮箱已存在（EMAIL_ALREADY_EXISTS）"},
        422: {"description": "参数校验失败（VALIDATION_ERROR）"},
    },
)
async def create_user(
    payload: UserCreate,
    request: Request,
    identity=Depends(require_roles("user", "admin")),
) -> UserOut:
    service = _user_service(request)
    user = await service.create_user(payload.email, payload.display_name, payload.vip_level)
    return _to_out(user)


@router.get(
    "/{user_id}",
    response_model=UserOut,
    responses={
        401: {"description": "未认证（默认拒绝）"},
        403: {"description": "仅本人或管理员可访问（数据级授权）"},
        404: {"description": "用户不存在（USER_NOT_FOUND）"},
    },
)
async def get_user(
    user_id: str,
    request: Request,
    identity=Depends(require_roles("user", "admin")),
) -> UserOut:
    service = _user_service(request)
    user = await service.get_user(user_id)  # 不存在时抛 USER_NOT_FOUND
    # 数据级授权（定律3）：仅本人或 admin
    ensure_owner(user.id, identity)
    return _to_out(user)