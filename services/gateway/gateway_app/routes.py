"""功能白名单路由（默认拒绝：不在白名单 = 拒绝）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import APIRouter, Request
from kernel.context import Identity
from kernel.errors import ForbiddenError

from .auth import verify_token
from .proxy import proxy_request

router = APIRouter(prefix="/v1", tags=["gateway"])


@dataclass(frozen=True)
class RouteRule:
    method: str
    path: str  # 支持 {param} 占位
    roles: tuple[str, ...] = ()


# 功能白名单：新增下游功能时，先登记这里（与契约同步），网关才放行
ROUTE_WHITELIST: list[RouteRule] = [
    RouteRule("POST", "/v1/users", ("user", "admin")),
    RouteRule("GET", "/v1/users/{user_id}", ("user", "admin")),
]


def check_function_access(method: str, path: str, identity: Identity) -> None:
    for rule in ROUTE_WHITELIST:
        if rule.method == method and _match(rule.path, path):
            if not rule.roles or (set(identity.roles) & set(rule.roles)):
                return
            raise ForbiddenError("角色无权访问该功能")
    raise ForbiddenError("功能不在白名单中")


def _match(pattern: str, path: str) -> bool:
    regex = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", pattern) + "$"
    return re.match(regex, path) is not None


def _settings(request: Request) -> object:
    return request.app.state.settings


@router.post("/users", status_code=201)
async def gateway_create_user(request: Request):
    settings = _settings(request)
    identity = verify_token(request.headers.get("authorization"), settings)
    check_function_access("POST", "/v1/users", identity)
    return await proxy_request("POST", "/v1/users", request, request.app.state.balancer, identity)


@router.get("/users/{user_id}")
async def gateway_get_user(user_id: str, request: Request):
    settings = _settings(request)
    identity = verify_token(request.headers.get("authorization"), settings)
    path = f"/v1/users/{user_id}"
    check_function_access("GET", path, identity)
    return await proxy_request("GET", path, request, request.app.state.balancer, identity)