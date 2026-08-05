"""统一异常体系（方向二：共性能力抽象化）。

所有业务错误必须继承 AppError，并携带注册表业务错误码（见 error_codes.py）。
错误通过 RFC 9457 Problem Details 返回（见 problem.py）。
业务码命名：UPPER_SNAKE，稳定不可变；前端据此分支，message 仅供展示。
"""
from __future__ import annotations

from typing import Any

from .error_codes import ErrorCode, get_error_code


class AppError(Exception):
    """业务异常基类：由注册表错误码驱动（HTTP 状态/title/默认消息/日志级别/可重试）。"""

    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        detail: Any = None,
        http_status: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        ec: ErrorCode | None = get_error_code(code) if code else get_error_code(self.error_code)
        self.error_code: str = ec.code if ec else (code or self.error_code)
        self.http_status: int = http_status or (ec.http_status if ec else 500)
        self.title: str = ec.title if ec else "Error"
        self.message: str = message or (ec.default_message if ec else self.error_code)
        self.detail: Any = detail
        self.retry_after: int | None = retry_after
        super().__init__(self.message)


class InternalError(AppError):
    error_code = "INTERNAL_ERROR"


class BadRequestError(AppError):
    error_code = "BAD_REQUEST"


class UnauthorizedError(AppError):
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    error_code = "FORBIDDEN"


class NotFoundError(AppError):
    error_code = "NOT_FOUND"


class ConflictError(AppError):
    error_code = "CONFLICT"


class ValidationError(AppError):
    error_code = "VALIDATION_ERROR"


class RateLimitError(AppError):
    error_code = "RATE_LIMITED"

    def __init__(self, message: str | None = None, *, retry_after: int = 60, **kwargs: Any) -> None:
        super().__init__(message, retry_after=retry_after, **kwargs)


class BadGatewayError(AppError):
    error_code = "BAD_GATEWAY"


class ServiceUnavailableError(AppError):
    error_code = "SERVICE_UNAVAILABLE"


class GatewayTimeoutError(AppError):
    error_code = "GATEWAY_TIMEOUT"


# 兼容别名（旧代码）
DownstreamError = BadGatewayError