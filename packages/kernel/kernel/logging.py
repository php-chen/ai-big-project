"""结构化 JSON 日志（定律5：全链路可观测）。

能力：
- ContextFilter：自动把请求上下文（request_id/trace_id/span_id/用户身份）注入每条日志；
- JsonFormatter：统一 JSON 结构 + 敏感字段脱敏 + service/env 标识；
- setup_logging：根 logger 统一 JSON 输出，关闭 uvicorn 原生访问日志（改由 AccessLogMiddleware 输出结构化访问日志）。

业务附加字段：logger.info("...", extra={"ctx": {"order_id": "..."}})
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from .context import get_identity, get_request_id, get_span_id, get_trace_id

_SENSITIVE_KEY = re.compile(
    r"(password|passwd|pwd|secret|token|authorization|api[_-]?key|cookie|credit[_-]?card)",
    re.IGNORECASE,
)

# 低频第三方日志降噪
_QUIET_LOGGERS = ("sqlalchemy.engine", "aiormq", "aio_pika", "watchfiles", "pika")

_BUILTIN_CTX_KEYS = ("request_id", "trace_id", "span_id", "user_id", "tenant_id")


class ContextFilter(logging.Filter):
    """自动附加请求上下文（定律5：所有日志强制绑定 request_id/trace_id）。

    业务通过 extra={"ctx": {...}} 传入的字段会合并，但内置上下文键优先（防止伪造）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        business = getattr(record, "ctx", None)
        if not isinstance(business, dict):
            business = {}

        identity = get_identity()
        ctx: dict[str, Any] = {
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
            "span_id": get_span_id(),
            "user_id": identity.user_id if identity else None,
            "tenant_id": identity.tenant_id if identity else None,
        }
        for key, value in business.items():
            if key not in _BUILTIN_CTX_KEYS:
                ctx[key] = value
        record.ctx = ctx
        return True


class JsonFormatter(logging.Formatter):
    def __init__(
        self,
        service_name: str = "",
        app_env: str = "",
        mask_secrets: bool = True,
    ) -> None:
        super().__init__()
        self._service_name = service_name
        self._app_env = app_env
        self._mask_secrets = mask_secrets

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service_name,
            "env": self._app_env,
            "message": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            for key, value in ctx.items():
                if value not in (None, ""):
                    payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if self._mask_secrets:
            payload = self._mask(payload)
        return json.dumps(payload, ensure_ascii=False, default=str)

    @classmethod
    def _mask(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ("***" if _SENSITIVE_KEY.search(key) else cls._mask(val))
                for key, val in value.items()
            }
        if isinstance(value, list):
            return [cls._mask(item) for item in value]
        return value


def setup_logging(
    level: str = "INFO",
    *,
    json_logs: bool = True,
    service_name: str = "",
    app_env: str = "",
    mask_secrets: bool = True,
    disable_uvicorn_access: bool = True,
) -> None:
    """配置根 logger：JSON 结构化输出到 stdout（12-Factor：日志进 stdout）。"""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(
            JsonFormatter(service_name=service_name, app_env=app_env, mask_secrets=mask_secrets)
        )
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(ContextFilter())
    root.addHandler(handler)

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    if disable_uvicorn_access:
        # 结构化访问日志由 AccessLogMiddleware 输出，关闭 uvicorn 原生访问日志
        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_access.disabled = True
        uvicorn_access.handlers.clear()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)