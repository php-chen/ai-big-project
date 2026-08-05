"""服务业务错误码（扩展注册表，单一事实来源）。

新增业务错误码：register_error_code(ErrorCode(code, http_status, title, default_message))
- code 必须 UPPER_SNAKE、稳定不可变（前端据此 switch）；
- 已被内核占用：INTERNAL_ERROR/BAD_REQUEST/UNAUTHORIZED/FORBIDDEN/NOT_FOUND/
  METHOD_NOT_ALLOWED/CONFLICT/VALIDATION_ERROR/RATE_LIMITED/BAD_GATEWAY/
  SERVICE_UNAVAILABLE/GATEWAY_TIMEOUT/HTTP_ERROR。
"""
from __future__ import annotations

from kernel.error_codes import ErrorCode, register_error_code

USER_NOT_FOUND = register_error_code(ErrorCode("USER_NOT_FOUND", 404, "User Not Found", "用户不存在"))
EMAIL_ALREADY_EXISTS = register_error_code(ErrorCode("EMAIL_ALREADY_EXISTS", 409, "Conflict", "邮箱已存在"))
USER_FORBIDDEN = register_error_code(ErrorCode("USER_FORBIDDEN", 403, "Forbidden", "无权访问该用户"))