# 负载均衡框架（三层）

微服务架构下负载均衡分三层，本项目各层实现如下：

```
                        ┌────────────┐
   客户端 ──> Nginx(80) │  边缘 LB    │  least_conn + 健康感知
                        └─────┬──────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
        gateway:8000    gateway-2:8000   gateway-3:8000   （功能白名单 + 身份注入 + trace）
              │               │                │
              └───────────────┼────────────────┘
                              │  客户端侧 LB（UpstreamBalancer）
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
   service-template:8100  template-2:8100  template-3:8100
              │               │                │
              ▼               ▼                ▼
        PostgreSQL 主库（写） ──WAL──> 从库副本（读，轮询）
```

## 1. 边缘层（Nginx）

- 位置：`deploy/nginx/nginx.conf`
- 策略：`least_conn` + 被动健康检查（`max_fails=3 fail_timeout=30s`，配合容器 HEALTHCHECK）；
- 职责：入口流量分发、X-Forwarded-* 头、X-Request-ID 透传、TLS 终止（配置已就绪，生产启用 443）；
- 编排：`deploy/docker-compose.prod.yml` 的 `nginx` 服务，上游为 3 个网关副本。

## 2. 服务间层（网关客户端侧 LB）

- 位置：`services/gateway/gateway_app/balancer.py`（`UpstreamBalancer`）
- 策略：
  - **轮询**（round-robin）选择健康实例；
  - **健康感知**：连接错误 / 5xx 连续达阈值（默认 3 次）标记不可用；
  - **半开恢复**：冷却期（默认 30s）后允许一次探活，成功即恢复（后台 `probe_loop` 定期探测 `/health/live`）；
  - **失败转移**：选中实例失败自动切换下一健康实例；
  - **连接池**：共享 `httpx.AsyncClient`（keep-alive），避免每请求新建连接。
- 配置：`UPSTREAM_SERVICE_URLS=http://service-template:8100,http://service-template-2:8100,...`（逗号分隔，优先于 `UPSTREAM_SERVICE_URL`）。

## 3. 数据层（读副本轮询）

- 位置：`packages/kernel/kernel/db.py`（`DatabaseRouter`）
- 策略：`read_factory` 在多个从库之间轮询；未配置副本自动降级主库；
- 配置：`REPLICA_DATABASE_URLS`（逗号分隔多个从库，优先于 `REPLICA_DATABASE_URL`）；
- 健康检查：`/health/ready` 的 `db_read` 至少一个从库可用即 ok。

## 4. 横向扩容的正确性（Outbox 单写者）

- 多个服务副本同时轮询 outbox 表会**重复投递事件**；
- 解决：`OutboxRelay` 使用 `SELECT ... FOR UPDATE SKIP LOCKED`（行锁 + 跳过已锁行），保证同一批消息只有一个副本投递；
- SQLite（开发）不支持 SKIP LOCKED，自动关闭该特性；PG 生产开启。

## 5. 扩容方式

```bash
# 副本已在生产编排中定义（service-template-2/3、gateway-2/3）
# 想加更多副本：复制服务定义（YAML 锚点）或改用 docker compose scale
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d
# 入口：http://<host>/  （Nginx 80 -> 网关副本 -> 服务副本）
```

## 6. 可观测性联动（定律5）

- 网关 balancer 每次选择实例输出 `kernel.access` 之外的 debug 日志（`upstream 选择: <url>`）；
- 配合 trace_id 可按链路观察请求实际命中哪个副本；
- 网关 `health_snapshot()` 可暴露实例健康状态（可接入监控面板）。