# 响应与错误规范（方向二决策）

> 状态编码体系（三层模型：HTTP 状态 / 业务码 / 明细）详见 `docs/standards/status-codes.md`。

## 成功响应 = 资源本体

- 返回 HTTP 语义码 + 资源 JSON（如 `200` + 用户对象）；
- **不使用** `{code, message, data}` 万能包装（会破坏 REST 语义与 OpenAPI 自动生成）。

## 错误响应 = RFC 9457 Problem Details

所有错误统一返回 `application/problem+json`：

```json
{
  "type": "/docs/errors#not_found",
  "title": "Not Found",
  "status": 404,
  "detail": "用户不存在",
  "code": "USER_NOT_FOUND",
  "instance": "/v1/users/u-1",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

## 错误码速查（HTTP 状态 -> 业务码）

| 状态 | code | 场景 |
|---|---|---|
| 400 | BAD_REQUEST | 请求不合法 |
| 401 | UNAUTHORIZED | 未认证（默认拒绝） |
| 403 | FORBIDDEN / USER_FORBIDDEN | 无数据级权限 / 不在功能白名单 |
| 404 | NOT_FOUND / USER_NOT_FOUND | 资源不存在（业务码细分） |
| 405 | METHOD_NOT_ALLOWED | 方法不允许 |
| 409 | CONFLICT / EMAIL_ALREADY_EXISTS | 冲突（业务码细分） |
| 422 | VALIDATION_ERROR | 参数校验失败（含字段级 errors） |
| 429 | RATE_LIMITED | 限流（带 retry_after） |
| 502 | BAD_GATEWAY | 网关下游不可达 |
| 503 | SERVICE_UNAVAILABLE | 依赖不可用 |
| 504 | GATEWAY_TIMEOUT | 下游超时 |
| 500 | INTERNAL_ERROR | 未知异常（脱敏） |

## 实现

- 业务代码抛 `kernel.errors.*`（`AppError` 子类），**必须携带注册表业务码**（`code=...`）；
- 由 `kernel.problem.register_exception_handlers` 统一转成 Problem Details；
- 未知异常记录完整堆栈，但只向客户端返回脱敏信息；
- `GET /errors` 可查看全量错误码（调试 / 前端枚举 / 文档生成）。