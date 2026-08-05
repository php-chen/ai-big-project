# 状态编码规范（三层模型）

与主流实践（RFC 9457 Problem Details + 稳定机器可读错误码）对齐：
**HTTP 状态码（传输语义） + 业务错误码（前端分支依据） + 错误明细（排错索引）**。

## 1. 三层模型

| 层 | 字段 | 作用 | 示例 |
|---|---|---|---|
| HTTP 状态码 | `status` | 传输语义（客户端/网关/负载均衡据此处理） | 401 / 404 / 409 / 429 |
| 业务错误码 | `code` | **稳定、机器可读、可扩展**，前端 switch 依据 | `EMAIL_ALREADY_EXISTS` |
| 错误明细 | `detail`/`errors`/`trace_id`/`type` | 排错与展示 | 字段级 errors、链路 ID、文档链接 |

```json
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
X-Error-Code: EMAIL_ALREADY_EXISTS

{
  "type": "/docs/errors#email_already_exists",
  "title": "Conflict",
  "status": 409,
  "detail": "邮箱已存在",
  "code": "EMAIL_ALREADY_EXISTS",
  "instance": "/v1/users",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

## 2. 业务错误码注册表（单一事实来源）

- 内核内置：`packages/kernel/kernel/error_codes.py`；
- 服务扩展：`services/*/app/error_codes.py` 调用 `register_error_code(ErrorCode(...))`；
- 自动产出：`GET /errors` 列出全部错误码（调试、生成前端枚举、文档）。

### 内置错误码

| code | HTTP | 含义 | retryable |
|---|---|---|---|
| BAD_REQUEST | 400 | 请求不合法 | |
| UNAUTHORIZED | 401 | 未认证（默认拒绝） | |
| FORBIDDEN | 403 | 无权访问 | |
| NOT_FOUND | 404 | 资源不存在 | |
| METHOD_NOT_ALLOWED | 405 | 方法不允许 | |
| CONFLICT | 409 | 资源冲突 | |
| VALIDATION_ERROR | 422 | 参数校验失败（含字段级 errors） | |
| RATE_LIMITED | 429 | 限流（带 retry_after） | ✅ |
| BAD_GATEWAY | 502 | 下游不可用 | ✅ |
| SERVICE_UNAVAILABLE | 503 | 服务不可用 | ✅ |
| GATEWAY_TIMEOUT | 504 | 下游超时 | ✅ |
| INTERNAL_ERROR | 500 | 未知异常（脱敏） | |
| HTTP_ERROR | - | 未映射的 HTTP 异常兜底 | |

### 业务码示例（service-template）

| code | HTTP | 场景 |
|---|---|---|
| EMAIL_ALREADY_EXISTS | 409 | 创建用户邮箱重复 |
| USER_NOT_FOUND | 404 | 查询用户不存在 |
| USER_FORBIDDEN | 403 | 数据级授权拒绝（用户维度） |

## 3. 如何新增错误码（扩展性）

```python
# services/<svc>/app/error_codes.py
from kernel.error_codes import ErrorCode, register_error_code

ORDER_NOT_FOUND = register_error_code(ErrorCode("ORDER_NOT_FOUND", 404, "Order Not Found", "订单不存在"))
```

规则：
- `code`：UPPER_SNAKE、**稳定不可变**（改名 = 破坏性变更，前端联动）；
- 不同业务码可映射同一 HTTP 状态（HTTP 是传输语义，code 是业务语义）；
- 不要重复占用内核内置码；语义相同优先复用。

## 4. 前端 / 客户端指引

- **用 `code` 分支，不要用 `message`**（message 仅供展示，可随时改文案）；
- 429/503/504 响应带 `retry_after`，可按此做退避重试；
- 422 的 `errors` 数组是字段级校验明细（`loc`/`msg`）；
- 排错入口：把 `trace_id` 交给后端，按链路聚合日志定位。

## 5. 使用约定（红线）

- 业务代码禁止直接 `return {"error": ...}`，必须抛 `AppError` 子类并带注册表 code；
- 禁止在错误 `detail` 中泄露内部信息（堆栈/连接串/密钥）；
- 未知异常统一 `INTERNAL_ERROR`（记录完整堆栈，客户端只见脱敏信息）；
- 网关返回 `X-Error-Code` 响应头，便于客户端/中间件快速识别。