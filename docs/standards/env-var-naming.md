# 环境变量命名规范（方向一）

> 所有微服务必须使用同一套命名。新增变量时先更新 `.env.example` 与本文档。

## 命名规则

1. 全小写下划线（`snake_case`），如 `database_url`；
2. 连接串统一 `<类型>_URL`：`DATABASE_URL` / `REDIS_URL` / `AMQP_URL`；
3. 布尔值统一 `TRUST_*` / `ENABLE_*` 前缀，值 `true/false`；
4. 敏感信息只通过环境变量/密钥管理注入，禁止写入代码或提交到仓库。

## 标准变量表

| 变量 | 必填 | 说明 |
|---|---|---|
| APP_ENV | ✅ | development/staging/production |
| APP_NAME | ✅ | 全局项目名 |
| SERVICE_NAME | ✅ | 每个服务唯一 |
| LOG_LEVEL | ✅ | DEBUG/INFO/WARNING/ERROR |
| DATABASE_URL | 按服务 | PostgreSQL 异步连接串 |
| REDIS_URL | 按服务 | 幂等/缓存 |
| AMQP_URL | 按服务 | RabbitMQ |
| TRUST_PROXY_HEADERS | 生产 ✅ | 信任网关注入身份头（须配 mTLS） |
| OTEL_EXPORTER_OTLP_ENDPOINT | 生产 ✅ | OTLP Collector 地址 |
| IDEMPOTENCY_TTL_SECONDS | 否 | 默认 3600 |

## 配置读取

- 一律通过 `kernel.config.Settings`（pydantic-settings）读取；
- 服务级扩展：继承 `Settings` 增加字段，禁止另起一套加载逻辑。