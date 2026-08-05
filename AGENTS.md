# AI 大项目 · 架构宪法（AGENTS）

> 本文件是**最高优先级约束**。任何 AI 或人类开发者生成的代码，都不得违反本文件中的任何一条定律。
> 修改本文件必须经过项目负责人书面确认。

## 0. 技术基线（方向一：地基环境标准化）

- Python 版本：**3.14**（虚拟环境 `.venv`，Python 3.14.5）
- Web 框架：**FastAPI** + Uvicorn
- 数据库：PostgreSQL 16 主从（读写分离），异步驱动 `psycopg`，ORM 用 SQLAlchemy 2.0 async；**写走主库、读走从库**（`REPLICA_DATABASE_URL`，未配置自动降级）
- 缓存/幂等存储：Redis 7
- 消息队列：RabbitMQ 3.x（AMQP）
- 迁移工具：Alembic
- 可观测性：OpenTelemetry（W3C `traceparent`）
- 环境变量命名：全小写下划线，连接串统一 `<类型>_URL`（见 `.env.example`）
- **任何服务连接中间件，都只从环境变量读取，禁止硬编码连接信息**

---

## 1. 五大顶层框架逻辑（物理定律，不可逾越）

### 定律 1：通信契约优先（Contract-First）

- 所有 HTTP 接口的入参/出参，必须在业务代码之前定义在 `contracts/` 层（OpenAPI）。
- 所有领域事件的消息体，必须在 `contracts/events/` 定义（JSON Schema）。
- AI 生成代码时**只能引用**契约定义，**严禁**在函数内部临时捏造字段名（如 `UserId` / `user_id` / `uid` 混用）。
- 契约演进规则：只允许**增量变更**；新增字段必须带默认值；破坏性变更必须升版本并保留兼容窗口。
- 线上契约（wire schema）与领域模型是两回事，禁止用契约类型替代领域模型。

### 定律 2：数据主权单向流（Data Ownership）

- 每个数据实体有且只有一个 Owner 服务；其他服务**绝不**在自己的数据库里冗余存储 Owner 的权威字段。
- 跨服务引用**只允许存 ID**（如订单只存 `user_id`，不存昵称/手机号）。
- 允许例外：**派生只读模型（Read Model）**——消费方服务可通过订阅事件维护自己的副本，但副本归消费方所有，且严禁在副本上实时 Join 其他服务。
- **严禁**任何服务直接访问其他服务的数据库表（跨库 Join = 红线）。
- 聚合策略：客户端侧用 BFF 聚合；高频聚合用事件驱动读模型；**禁止让网关做大量数据聚合**。

### 定律 3：权限二维防线 + 信任边界

- **网关管功能（能不能访问这个 URL）**：白名单 + 角色粗粒度校验。
- **业务管数据（能不能看到这条数据）**：服务内**默认拒绝**，按属主/租户/ACL 显式授权。
- 业务服务**不重复校验功能级权限**，只做数据级校验。
- **信任边界**：网关验证令牌后注入可信头 `X-User-Id` / `X-User-Roles` / `X-Tenant-Id`；业务服务只信这些头，**绝不信任客户端自带的身份头**。
- `TRUST_PROXY_HEADERS=true` 且网关与服务间启用 mTLS/服务网格后，业务服务才接受注入头；否则一律视为未认证（默认拒绝）。

### 定律 4：最终一致性 + 事务发件箱（Outbox）

- **绝不使用 XA/强一致分布式事务**。
- 范式：**本地事务 + 领域事件（异步消息）**。跨服务失败走补偿/重试，**不直接回滚主服务**。
- 本地事务与发消息必须原子：先写业务表 + `outbox_messages` 表（同一事务），由 Outbox Relay 异步投递。**禁止在事务提交前直接发 MQ**。
- 所有产生副作用的接口必须支持 `Idempotency-Key`；消费者按 **at-least-once + 幂等消费** 设计。
- 重试策略：指数退避 + 最大重试次数 + 死信队列。
- 事件也是契约：事件名必须带版本（如 `user.created.v1`），消息体 schema 在 `contracts/events/`。

### 定律 5：可观测性基因（全链路追踪）

- 使用 **OpenTelemetry（W3C `traceparent`）**，禁止自造 TraceID 头。
- 网关生成/延续 Trace，**所有服务调用下游必须在协议头透传 trace 上下文**；MQ 消息头必须带 trace 上下文。
- 日志必须为**结构化 JSON**，且每条日志绑定 `request_id` / `trace_id`。
- Python 下 trace 上下文必须用 `contextvars` 传播（asyncio 禁用线程局部变量）。
- 每个服务必须暴露 `/health/live`（存活）和 `/health/ready`（就绪，含依赖检查）。
- 日志规范见 `docs/standards/logging.md`：结构化 JSON、自动关联 ID、敏感字段脱敏、访问日志、慢查询日志。
- 状态码规范见 `docs/standards/status-codes.md`：三层模型（HTTP 状态 / 业务码 / 明细），错误必须抛 `AppError` 并携带注册表业务码，禁止在 detail 泄露内部信息。

---

## 2. 四大工作方向

1. **环境标准化**：所有服务共用 `.env.example` 模板，版本下限见 docker-compose.yml。
2. **共性能力抽象化**：只允许从 `packages/kernel` 引用共享能力；内核**零业务属性**，禁止内核 import 任何业务模型；内核版本化、API 面最小化、严格向后兼容。
3. **数据演进版本化**：数据库变更走 **Expand-Contract**（加可空/带默认值字段 → 双写双读 → 回填 → 收紧 → 清理旧列）；**任何新增字段必须带默认值，旧代码对新字段无感知**；pydantic 模型 `extra="ignore"`。
4. **AI 协作锚点化**：每个服务必须有一份“模块说明书”（`docs/module-specs/`），包含六要素：API 契约、核心表 ER、数据归属边界、发布/订阅事件、5 条定律摘要、非功能要求与完成定义。**禁止**让 AI 在单个会话中理解整个系统。

---

## 3. 仓库结构

```
project-map.yaml            # 项目地图（机器可读单一事实来源，CI 校验防漂移）
contracts/                  # 契约层（唯一事实来源）
  http/*.openapi.yaml       #   HTTP 契约
  events/*.schema.json      #   事件契约
packages/
  kernel/                   # 共享内核（零业务属性）
  contract-sdk/             # 契约 SDK（从 contracts/ 生成，含事件信封）
services/
  gateway/                  # API 网关（功能白名单 + 身份注入 + 代理）
  service-template/         # 服务模板（新服务以此为起点）
tests/                      # 根级自动测试（契约/边界/集成/端到端）
docs/                       # 架构文档、标准规范、模块说明书
scripts/                    # 统一命令
```

## 4. 新增一个微服务的固定流程

1. 复制 `services/service-template` 为 `services/<name>`。
2. 在 `contracts/http/` 定义该服务的 OpenAPI 契约（先写契约！）。
3. 在 `contracts/events/` 定义它发布/订阅的事件 schema。
4. 在 `docs/architecture/02-ownership-matrix.md` 登记数据归属。
5. 编写模块说明书（六要素）。
6. 实现业务代码：**只引用契约 SDK 与内核，只访问自己的表，本地事务 + Outbox 发事件，默认拒绝授权，透传 trace**。
7. 在 `tests/conftest.py` 的 `SERVICE_PACKAGES` 登记新服务（边界扫描自动覆盖）。
8. 通过 `scripts\test.ps1`（unit）与 `scripts\lint.ps1` 后方可提交。

## 5. 代码生成红线（AI 违规自查清单）

- [ ] 是否在业务代码里临时捏造了契约外的字段？
- [ ] 是否跨服务访问了别人的数据库表？（红线）
- [ ] 是否在业务层重复校验功能级权限？
- [ ] 是否在事务提交前直接发 MQ？（必须走 Outbox）
- [ ] 是否对副作用接口实现了幂等？
- [ ] 是否透传了 trace 上下文？日志是否带 request_id/trace_id？
- [ ] 新增字段是否带了默认值？pydantic 是否 `extra="ignore"`？
- [ ] 是否硬编码了环境变量/连接信息？
- [ ] 新增/修改服务、包、契约、事件、表归属后，是否同步更新了 `project-map.yaml`？（CI 校验）

## 6. 自动化测试纪律（边界由机器守）

- 所有代码变更必须通过 `scripts\test.ps1`（默认 unit 级）+ `scripts\lint.ps1`；
- 合并到 main 前必须通过 CI（unit + contract + boundary + e2e；集成测试在 push 时执行）；
- 新增服务/表/事件时，按 `docs/standards/testing.md` 同步登记边界测试；
- 边界扫描是“物理定律的执法者”：跨服务 import、表归属冲突、硬编码连接串 = CI 直接失败。
- 部署纪律：生产必须先 lembic upgrade head（仅增量迁移）再滚动更新；镜像走 deploy/ 编排；回滚 = 指定上一版本 TAG 重跑 deploy/deploy.sh。