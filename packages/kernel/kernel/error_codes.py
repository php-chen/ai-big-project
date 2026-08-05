"""业务错误码注册表（单一事实来源）。

三层状态编码模型：
1. HTTP 状态码：传输语义（400/401/403/404/409/422/429/5xx...）；
2. 业务错误码：机器可读、稳定、可扩展（如 USER_NOT_FOUND），前端据此分支；
3. 错误明细：RFC 9457 Problem Details（detail / errors / trace_id / 文档链接）。

新增业务错误码：register_error_code(ErrorCode(...)) 即可（见 services/*/app/error_codes.py）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCode:
    code: str                # 机器可读业务码（UPPER_SNAKE，稳定，前端据此 switch）
    http_status: int         # HTTP 状态码（传输语义）
    title: str               # RFC9457 title（简短）
    default_message: str     # 默认 detail
    log_level: str = "warning"   # 记录日志的级别
    retryable: bool = False  # 是否可安全重试（429/503/504 等）


_REGISTRY: dict[str, ErrorCode] = {}


def register_error_code(error_code: ErrorCode) -> ErrorCode:
    """注册业务错误码（幂等；重复注册以首次为准）。"""
    _REGISTRY.setdefault(error_code.code, error_code)
    return error_code


def get_error_code(code: str) -> ErrorCode | None:
    return _REGISTRY.get(code)


def all_error_codes() -> list[ErrorCode]:
    return sorted(_REGISTRY.values(), key=lambda ec: (ec.http_status, ec.code))


# ===== 内置通用错误码 =====
INTERNAL_ERROR = register_error_code(ErrorCode("INTERNAL_ERROR", 500, "Internal Server Error", "服务器内部错误", log_level="error"))
BAD_REQUEST = register_error_code(ErrorCode("BAD_REQUEST", 400, "Bad Request", "请求不合法"))
UNAUTHORIZED = register_error_code(ErrorCode("UNAUTHORIZED", 401, "Unauthorized", "未认证：缺少可信身份", log_level="info"))
FORBIDDEN = register_error_code(ErrorCode("FORBIDDEN", 403, "Forbidden", "无权访问该资源", log_level="info"))
NOT_FOUND = register_error_code(ErrorCode("NOT_FOUND", 404, "Not Found", "资源不存在", log_level="info"))
METHOD_NOT_ALLOWED = register_error_code(ErrorCode("METHOD_NOT_ALLOWED", 405, "Method Not Allowed", "请求方法不被允许", log_level="info"))
CONFLICT = register_error_code(ErrorCode("CONFLICT", 409, "Conflict", "资源冲突"))
VALIDATION_ERROR = register_error_code(ErrorCode("VALIDATION_ERROR", 422, "Validation Error", "请求参数校验失败"))
RATE_LIMITED = register_error_code(ErrorCode("RATE_LIMITED", 429, "Too Many Requests", "请求过于频繁，请稍后再试", retryable=True))
BAD_GATEWAY = register_error_code(ErrorCode("BAD_GATEWAY", 502, "Bad Gateway", "下游服务不可用", retryable=True))
SERVICE_UNAVAILABLE = register_error_code(ErrorCode("SERVICE_UNAVAILABLE", 503, "Service Unavailable", "服务暂不可用，请稍后再试", retryable=True))
GATEWAY_TIMEOUT = register_error_code(ErrorCode("GATEWAY_TIMEOUT", 504, "Gateway Timeout", "下游服务响应超时", retryable=True))
HTTP_ERROR = register_error_code(ErrorCode("HTTP_ERROR", 500, "HTTP Error", "HTTP 错误"))


def lookup_http_error(status: int) -> ErrorCode:
    """按 HTTP 状态码反查标准错误码（用于 Starlette 默认异常等）。"""
    by_status = {
        400: BAD_REQUEST,
        401: UNAUTHORIZED,
        403: FORBIDDEN,
        404: NOT_FOUND,
        405: METHOD_NOT_ALLOWED,
        409: CONFLICT,
        422: VALIDATION_ERROR,
        429: RATE_LIMITED,
        500: INTERNAL_ERROR,
        502: BAD_GATEWAY,
        503: SERVICE_UNAVAILABLE,
        504: GATEWAY_TIMEOUT,
    }
    return by_status.get(status, HTTP_ERROR)