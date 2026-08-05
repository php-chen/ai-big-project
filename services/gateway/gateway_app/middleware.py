"""网关功能级白名单中间件（定律3：默认拒绝，路由之前拦截）。

在边缘统一校验“能不能访问这个 URL”，不在白名单的方法/路径直接 403，
避免把判断散落在每个路由里。
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from kernel.errors import AppError
from kernel.problem import problem_document

from .auth import verify_token
from .routes import check_function_access


class FunctionWhitelistMiddleware:
    def __init__(self, app: Any, settings: Any) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope.get("path", "").startswith("/v1/"):
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            try:
                identity = verify_token(headers.get("authorization"), self.settings)
                check_function_access(scope.get("method", ""), scope.get("path", ""), identity)
            except AppError as exc:
                response = JSONResponse(
                    status_code=exc.http_status,
                    media_type="application/problem+json",
                    content=problem_document(
                        title=exc.title,
                        status=exc.http_status,
                        detail=exc.message,
                        code=exc.error_code,
                        instance=scope.get("path", ""),
                    ),
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)