"""请求级上下文（contextvars，定律5：asyncio 禁用线程局部变量）。

RequestContextMiddleware 在请求进入时写入，日志/业务代码通过 get_* 读取。
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("span_id", default="")


@dataclass(frozen=True)
class Identity:
    """网关注入的可信身份（定律3：业务只信注入头，默认拒绝）。"""

    user_id: str | None = None
    roles: tuple[str, ...] = ()
    tenant_id: str | None = None
    is_service: bool = False


identity_var: contextvars.ContextVar[Identity | None] = contextvars.ContextVar("identity", default=None)


def set_request_context(request_id: str, trace_id: str = "", span_id: str = "") -> None:
    request_id_var.set(request_id)
    trace_id_var.set(trace_id)
    span_id_var.set(span_id)


def get_request_id() -> str:
    return request_id_var.get()


def get_trace_id() -> str:
    return trace_id_var.get()


def get_span_id() -> str:
    return span_id_var.get()


def set_identity(identity: Identity | None) -> None:
    identity_var.set(identity)


def get_identity() -> Identity | None:
    return identity_var.get()


def logging_context() -> dict[str, str]:
    """日志附加字段：确保每条日志绑定 request_id / trace_id。"""
    return {"request_id": get_request_id(), "trace_id": get_trace_id()}