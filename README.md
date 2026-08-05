# AI 大项目（服务端框架）

基于 **Python 3.14 + FastAPI** 的微服务 monorepo，以“契约优先 + 数据主权 + 双层鉴权 + 最终一致性 + 可观测性”五大物理定律为地基（详见 [AGENTS.md](AGENTS.md) 与 `docs/architecture/`）。

> 📘 **想了解这个项目是怎么从 0 搭起来的？** 看 [《好的项目地基应该怎么搭》——完整实战复盘](docs/foundation-playbook.md)（架构决策 / 建设顺序 / 22 个踩坑 / 10 条方法论 / 新项目 Checklist）。

## 项目地图`n`n> 给开发者 / 产品 / AI / 测试的全局导航：**机器可读** `project-map.yaml`（CI 校验防漂移）+ **人读全景** [docs/index.md](docs/index.md)（Mermaid 架构/链路/事件/数据 ER）+ 可搜索文档站（`scripts\docs.ps1`）。`n`n- **5 分钟看懂项目**：见 [docs/index.md](docs/index.md)`n- **新增/修改模块必须同步更新** `project-map.yaml`（CI 校验，不一致 = 失败）`n`n---`n`n## 快速开始

```powershell
# 一键初始化（创建虚拟环境 + 可编辑安装所有本地包/服务 + 测试依赖）
scripts\setup.ps1

# 启动中间件（PostgreSQL 主从 / Redis / RabbitMQ）
docker compose up -d

# 复制环境变量模板
Copy-Item .env.example .env

> 说明：`requirements.txt` 为第三方依赖锁定；本地包（kernel / contract-sdk / 各服务）由 `setup.ps1` 可编辑安装。
```

## 一键脚本

| 命令 | 作用 |
|---|---|
| `scripts\setup.ps1` | 创建虚拟环境并安装全部依赖 |
| `scripts\dev.ps1` | 启动服务模板（热重载，端口 8100） |
| `scripts\gateway.ps1` | 启动 API 网关（端口 8000） |
| `scripts\test.ps1` | 分层测试（默认 unit；`-Level contract/integration/e2e/all`） |
| `scripts\coverage.ps1` | 覆盖率报告（可选 `-FailUnder 60` 门槛） |
| scripts\docker-build.ps1 | 本地构建生产镜像（-Tag/-Registry） |
| scripts\lint.ps1 | ruff 静态检查 |
| scripts\codegraph.ps1 | CodeGraph 代码索引（-Init/-Sync/-Explore/-Node） |

## 分层架构（洋葱模型）

```
契约层 contracts/        线上报文与事件 schema（唯一事实来源，人人可见，可 codegen）
   ↓ 生成
契约 SDK contract-sdk/   事件信封 + 各域 schema（pydantic）
   ↓ 依赖
共享内核 kernel/         配置/日志/追踪/异常/鉴权/DB/Outbox/事件/健康（零业务属性）
   ↓ 依赖
领域服务 services/       业务逻辑（各服务私有，禁止跨服务 import）
```

详见 docs/architecture/03-onion-boundary.md。

## 数据库设计（读写分离）

- **PostgreSQL 16 主从 + SQLAlchemy 2.0 async**：写会话走主库，读会话走从库（REPLICA_DATABASE_URL），未配置副本自动降级。
- 路由规则与一致性语义见 docs/standards/database.md（读己之写、副本滞后接受、Outbox 强制主库）。
- 主从流复制编排见 docker-compose.yml（dev）与 deploy/docker-compose.prod.yml（prod）。

## 当前骨架

- `contracts/` —— HTTP + 事件契约示例与演进规则
- `packages/kernel/` —— 共享内核（可运行、有测试）
- `packages/contract-sdk/` —— 事件信封与示例 schema
- `services/service-template/` —— 服务模板（用户服务示例：本地事务 + Outbox 发布 `user.created.v1`）
- `services/gateway/` —— API 网关（功能白名单 + 身份注入 + 反向代理 + trace 透传）
- `docs/` —— 5 条定律、归属矩阵、洋葱边界、标准规范、模块说明书模板

## 自动化测试

以**微服务边界**为核心的分层测试框架：

- **单元**：各包/服务内部行为（无依赖）
- **契约**：事件 payload 严格符合 JSON Schema；HTTP 实现覆盖契约（定律1）
- **边界扫描**：跨服务 import 禁令、表归属唯一、网关零数据访问、禁止硬编码连接串（定律2/方向一/二）
- **集成**：testcontainers 拉起真实 PostgreSQL/Redis/RabbitMQ，验证 Outbox 全链路（定律4，需 Docker）
- **端到端**：网关→服务 全链路 401/201/403/幂等/trace（定律3/5，自动起子进程）

详见 `docs/standards/testing.md`，CI 见 `.github/workflows/ci.yml`。

## 自动化部署

基于项目特点（微服务 monorepo、零停机演进、可观测性）的部署方案见 [deploy/README.md](deploy/README.md)：

- **生产编排**：deploy/docker-compose.prod.yml（中间件 + 一次性迁移任务 + 服务 + 可选 OTel Collector）
- **镜像**：非编辑安装、非 root、内置健康检查（Dockerfile + .dockerignore）
- **CD**：.github/workflows/deploy.yml（push main -> 构建镜像推 GHCR -> SSH 滚动发布）
- **零停机**：先 lembic upgrade head（仅增量变更），再滚动更新服务；回滚 = 指定上一版本 TAG 重跑 deploy/deploy.sh。

## 日志与可观测性

- 结构化 JSON 日志：自动关联 equest_id/trace_id/span_id/用户身份，敏感字段脱敏，访问日志 + 慢查询日志（定律5）。
- 规范见 docs/standards/logging.md；OTel 接入见 deploy/otel-collector.yaml。

## 负载均衡（三层）

- **边缘**：Nginx 分发到网关副本（deploy/nginx/nginx.conf，least_conn + 健康感知 + TLS 就绪）。
- **服务间**：网关 UpstreamBalancer 客户端侧 LB——轮询 + 失败转移 + 半开恢复 + 连接池（UPSTREAM_SERVICE_URLS 多副本）。
- **数据层**：DatabaseRouter 多从库读轮询（REPLICA_DATABASE_URLS）。
- **扩容正确性**：Outbox Relay 用 FOR UPDATE SKIP LOCKED 保证多副本单写者，避免重复投递。

详见 docs/standards/load-balancing.md。

## 动态扩容（高峰期防爆）

- **闭环**：服务 /metrics → 自动扩缩器（RPS/错误率 + 持续确认 + 冷却 + 上下限）→ docker compose --scale → 新副本注册中心心跳 → 网关动态发现接入。
- 组件：kernel/metrics.py（指标）、kernel/registry.py（注册中心）、services/autoscaler/（扩缩器）、scripts/load-gen.ps1（压测）。
- 详见 docs/standards/dynamic-scaling.md。

## 资源监控

- **三层**：node-exporter（宿主机）+ cAdvisor（容器）+ 应用 /metrics（QPS/错误率/P95/在途/Outbox 积压）。
- **组件**：Prometheus（抓取+告警规则）、Grafana（自动供给资源/应用大盘）、告警规则见 deploy/monitoring/。
- 启用：docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod --profile monitoring up -d。
- 详见 docs/standards/resource-monitoring.md。

## 状态编码（三层模型）

- **HTTP 状态码**（传输语义）+ **业务错误码**（稳定机器可读，如 EMAIL_ALREADY_EXISTS）+ **错误明细**（RFC 9457 + trace_id + 文档链接）。
- 集中式错误码注册表：GET /errors 查看全量；新增码 = egister_error_code(ErrorCode(...)) 一行。
- 详见 docs/standards/status-codes.md。
