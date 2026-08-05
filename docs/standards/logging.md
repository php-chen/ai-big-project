# 日志规范（定律5：可观测性基因）

所有服务日志统一走 `kernel.logging`，**JSON 结构化 + 自动关联 ID + 敏感字段脱敏**。

## 1. 统一字段

| 字段 | 说明 | 来源 |
|---|---|---|
| ts | UTC ISO8601 时间 | 自动 |
| level | DEBUG/INFO/WARNING/ERROR | 自动 |
| logger | 日志器名（如 kernel.access） | 自动 |
| service | 服务名（SERVICE_NAME） | setup_logging |
| env | 环境（APP_ENV） | setup_logging |
| message | 日志正文 | 代码 |
| request_id | 请求 ID（网关/入口生成） | ContextFilter 自动 |
| trace_id | W3C trace id | ContextFilter 自动 |
| span_id | 当前 span id | ContextFilter 自动 |
| user_id / tenant_id | 可信身份 | ContextFilter 自动 |
| 业务字段 | 任意（order_id 等） | `extra={"ctx": {...}}` |

## 2. 自动关联 ID（ContextFilter）

- 所有日志**自动**附带 `request_id/trace_id/span_id/user_id/tenant_id`，无需手动传参；
- 业务附加字段：`logger.info("创建订单", extra={"ctx": {"order_id": "o-1"}})`；
- **内置键不可被业务覆盖**（防伪造关联 ID）。

## 3. 敏感字段脱敏

匹配以下键名的字段值自动替换为 `***`（递归）：
`password / passwd / pwd / secret / token / authorization / api_key / cookie / credit_card`

> 注意：脱敏只作用于结构化字段；**敏感值请勿直接拼进 message**，应放 ctx 或先手动打码。

## 4. 结构化访问日志

- uvicorn 原生访问日志已关闭，统一由 `AccessLogMiddleware` 输出（logger=`kernel.access`）；
- 字段：method / path / status / duration_ms / client_ip + 自动关联 ID。

```json
{"ts":"...","level":"INFO","logger":"kernel.access","service":"service-template",
 "message":"access","method":"POST","path":"/v1/users","status":201,
 "duration_ms":42.3,"request_id":"...","trace_id":"..."}
```

## 5. 慢查询日志

- `LOG_SLOW_QUERY_MS`（默认 0=关闭）>0 时，主/从引擎记录慢查询；
- 字段：duration_ms / sql（截断 500）/ engine（write/read）+ 关联 ID。

## 6. 使用规范（红线）

- 一律用 `kernel.logging.get_logger(__name__)`，禁止 print；
- 关键业务节点（创建/支付/失败/补偿）必须打结构化日志，**禁止空 message 无字段**；
- 禁止把密码/Token 拼进日志（含 message 与 ctx）；
- 日志进 stdout（12-Factor），由容器/采集器（如 Loki/ELK）统一收集；
- 排错入口：按 `trace_id` 聚合整条链路日志（定律5）。

## 7. 配置

| 环境变量 | 默认 | 说明 |
|---|---|---|
| LOG_LEVEL | INFO | 日志级别 |
| LOG_JSON | true | 是否 JSON 结构化 |
| LOG_ACCESS | true | 是否输出访问日志 |
| LOG_SLOW_QUERY_MS | 0 | 慢查询阈值（>0 开启） |