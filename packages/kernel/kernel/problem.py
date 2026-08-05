"""RFC 9457 Problem Details 错误响应（方向二决策：错误统一用 problem+json）。

三层模型：
- HTTP 状态码：status（传输语义）
- 业务错误码：code（稳定机器可读，前端 switch）
- 错误明细：detail / errors（字段级）/ instance / trace_id / type（文档链接）

成功响应 = 资源本体（REST 语义）。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .context import get_request_id, get_trace_id
from .error_codes import ErrorCode, all_error_codes, get_error_code, lookup_http_error
from .errors import AppError

logger = logging.getLogger(__name__)


def problem_document(
    *,
    title: str,
    status: int,
    detail: str,
    code: str,
    instance: str = "",
    trace_id: str | None = None,
    errors: Any = None,
    retry_after: int | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        # type 指向错误码文档页（调试/排查索引）
        "type": f"/docs/errors#{code.lower()}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "instance": instance,
        "trace_id": trace_id or get_trace_id(),
    }
    if errors is not None:
        doc["errors"] = errors
    if retry_after is not None:
        doc["retry_after"] = retry_after
    return doc


def _problem_response(request: Request, ec: ErrorCode, *, detail: str | None = None, errors: Any = None, retry_after: int | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=ec.http_status,
        media_type="application/problem+json",
        headers={"X-Error-Code": ec.code},
        content=problem_document(
            title=ec.title,
            status=ec.http_status,
            detail=detail or ec.default_message,
            code=ec.code,
            instance=str(request.url.path),
            errors=errors,
            retry_after=retry_after,
        ),
    )


def errors_router() -> APIRouter:
    """错误码清单端点：便于调试 / 生成前端枚举 / 文档。"""

    router = APIRouter(tags=["errors"])

    @router.get("/errors")
    async def list_error_codes() -> dict[str, Any]:
        return {
            "model": "RFC 9457 Problem Details",
            "note": "code 为稳定业务错误码（前端据此分支）；message 仅供展示",
            "codes": [
                {
                    "code": ec.code,
                    "http_status": ec.http_status,
                    "title": ec.title,
                    "default_message": ec.default_message,
                    "retryable": ec.retryable,
                    "log_level": ec.log_level,
                }
                for ec in all_error_codes()
            ],
        }

    return router


def register_exception_handlers(app: FastAPI) -> None:
    """注册统一异常处理：AppError / HTTPException / 校验错误 / 未知异常。"""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        ec = get_error_code(exc.error_code)
        if ec is None:
            ec = ErrorCode(exc.error_code, exc.http_status, exc.title, exc.message)
        logger.log(
            getattr(logging, ec.log_level.upper(), logging.WARNING),
            "%s: %s",
            exc.error_code,
            exc.message,
            extra={"ctx": {"request_id": get_request_id(), "trace_id": get_trace_id()}},
        )
        return _problem_response(request, ec, detail=exc.message, errors=exc.detail, retry_after=exc.retry_after)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        ec = lookup_http_error(exc.status_code)
        return _problem_response(request, ec, detail=str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        ec = get_error_code("VALIDATION_ERROR")
        return _problem_response(request, ec, errors=exc.errors())

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # 未知异常：记录完整堆栈，但只向客户端返回脱敏信息（默认拒绝原则）
        logger.exception(
            "unhandled exception: %s %s",
            request.method,
            request.url.path,
            extra={"ctx": {"request_id": get_request_id(), "trace_id": get_trace_id()}},
        )
        ec = get_error_code("INTERNAL_ERROR")
        return _problem_response(request, ec)