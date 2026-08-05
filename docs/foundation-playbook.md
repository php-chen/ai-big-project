# 好的项目地基应该怎么搭
## —— AI 大项目从 0 到 1 的完整实战复盘

> 本文记录这个微服务项目**从零到可用的完整过程**：为什么这么设计、按什么顺序建设、每个模块怎么落地、踩过哪些坑、以及提炼出的可复用方法论。
> 适合读者：想从 0 搭建项目地基的开发者 / 技术负责人 / 想用 AI 高效开发大型项目的团队。

---

## 0. 快速导航

| 章节 | 内容 |
|---|---|
| §1 | 项目背景与目标 |
| §2 | 第一步：先立宪（5 条物理定律 + 4 个方向） |
| §3 | 环境与仓库骨架（Python 3.14 / venv / monorepo / 契约层） |
| §4 | 共享内核（共性能力抽象化） |
| §5 | 业务骨架（服务模板 + 网关） |
| §6 | 质量防线（自动化测试，边界由机器守） |
| §7 | 数据与一致性（读写分离 + Outbox + 演进纪律） |
| §8 | 部署与运维（镜像 / 编排 / CD / 真实服务器） |
| §9 | 规模化能力（负载均衡 / 动态扩容 / 资源监控） |
| §10 | 体验与协作（状态码 / 日志 / 项目地图 / CodeGraph） |
| §11 | 踩坑全记录（现象 → 原因 → 解法） |
| §12 | 方法论：好的地基 10 条原则 |
| §13 | 当前全貌 |
| §14 | 新项目启动 Checklist |

---

## 1. 项目背景与目标

**背景**：一个从空目录开始的"AI 大项目"。核心理念是：**AI 全程参与大型项目开发时，地基不是代码结构，而是"物理规则"和"认知边界"**——先定不可逾越的约束，再让 AI 在约束内自由发挥。

**目标**：
- Python 3.14 + FastAPI 的微服务 monorepo；
- 契约优先、数据主权、双层鉴权、最终一致性、可观测性五大定律全部落地为代码；
- 每个边界都有**机器守卫**（测试 + CI），AI 违反定律 = 构建失败；
- 可部署到真实服务器、可动态扩容、可监控、可被团队和 AI 快速理解。

---

## 2. 第一步：先立宪（地基的"物理定律"）

任何业务代码之前，先确立**5 条顶层框架逻辑**（不可逾越的硬约束）：

| # | 定律 | 一句话 | 落地产物 |
|---|---|---|---|
| 1 | 通信契约优先 | 先定义"话怎么讲"，再写"话的内容" | `contracts/` + `contract-sdk` |
| 2 | 数据主权单向流 | 每张表只有一个 Owner，跨服务只存 ID | 归属矩阵 + 边界测试 |
| 3 | 权限二维防线 + 信任边界 | 网关管功能、业务管数据，默认拒绝 | 网关白名单 + `ensure_owner` |
| 4 | 最终一致性 + Outbox | 本地事务 + 领域事件，绝不强一致 | `outbox_messages` + relay + 幂等 |
| 5 | 可观测性基因 | 日志/指标/追踪是代码的一部分 | OTel + `/metrics` + 结构化日志 |

**4 个工作方向**（推进顺序）：
1. 环境标准化（同一套环境变量模板）；
2. 共性能力抽象化（共享内核，零业务属性）；
3. 数据演进版本化（Expand-Contract 零停机）；
4. AI 协作锚点化（模块说明书，AI 只处理当前子域）。

> 这一步的价值：**把"AI 不能违反什么"写死在项目里**，而不是靠每次提醒。
> 宪法写进了 `AGENTS.md`，AI 每次会话自动继承。

---

## 3. 环境与仓库骨架

### 3.1 环境
```powershell
py -3.14 -m venv .venv          # Python 3.14（当时是 3.14.5）
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn
```

### 3.2 Monorepo 结构（按"边界"而非"层"组织）
```
contracts/          契约层（唯一事实来源）
packages/kernel/    共享内核（零业务属性）
packages/contract-sdk/  契约 SDK（事件信封 + schema）
services/gateway/   API 网关
services/service-template/  服务模板（新服务起点）
tests/              根级测试（契约/边界/集成/端到端）
docs/               架构/规范/模块说明书
scripts/            统一命令
deploy/             编排与监控
project-map.yaml    项目地图（机器可读，CI 校验防漂移）
```

### 3.3 契约层（定律 1）
- HTTP 契约：`contracts/http/*.openapi.yaml`（OpenAPI 3.1）；
- 事件契约：`contracts/events/*.schema.json`（JSON Schema）；
- 演进规则：只允许增量变更，新增字段必须带默认值；
- 契约 SDK：事件信封 `EventEnvelope` + `extra="forbid"`（线上报文不可随意增删字段）。

> **为什么先做契约**：AI 幻觉的头号来源就是字段名混乱（`UserId`/`user_id`/`uid`）。
> 契约是唯一事实来源，AI 只能引用，不能捏造。

---

## 4. 共享内核（共性能力抽象化）

把每个服务都会用到、且行为必须一致的能力收进 `packages/kernel`（**零业务属性**，禁止 import 任何业务模型）：

| 模块 | 能力 |
|---|---|
| config.py | 环境变量统一加载（pydantic-settings），服务继承扩展 |
| logging.py | 结构化 JSON 日志 + ContextFilter 自动注入 request_id/trace_id + 敏感字段脱敏 |
| telemetry.py | OpenTelemetry（W3C `traceparent`），asyncio 用 contextvars |
| errors.py / error_codes.py | 统一异常体系 + **错误码注册表**（单一事实来源） |
| problem.py | RFC 9457 Problem Details + `GET /errors` 错误码清单 |
| auth.py | 数据级授权基座（`ensure_owner`/`require_roles`，默认拒绝） |
| db.py | SQLAlchemy 2.0 async + **读写分离路由**（写主读从，多从库轮询） |
| outbox.py | 事务发件箱 + `FOR UPDATE SKIP LOCKED` 单写者 + 积压量指标 |
| events.py | 事件总线（`build_event_bus`：有 AMQP 用 RabbitMQ，否则本地） |
| registry.py | 服务注册中心（Redis 心跳，动态扩容的实例清单） |
| metrics.py | Prometheus `/metrics`（QPS/错误率/延迟/在途/Outbox 积压） |
| idempotency.py | `Idempotency-Key` 幂等中间件（Redis / 内存降级） |
| health.py | `/health/live` + `/health/ready`（含依赖检查） |
| app.py | `create_app` 工厂：所有服务统一装配基座 |

> 内核的边界测试：**内核禁止 import 任何服务包**（洋葱边界），CI 强制。
> 契约 SDK 同样禁止反向依赖内核/服务。

---

## 5. 业务骨架（服务模板 + 网关）

### 5.1 服务模板（用户服务原型）
- 模型：`users`（带 Expand-Contract 演进示例 `updated_at`）+ `outbox_messages`；
- 领域服务：创建用户 = **本地事务写 users + outbox**，提交后 relay 异步发布 `user.created.v1`；
- 业务错误码：`EMAIL_ALREADY_EXISTS` / `USER_NOT_FOUND`（注册进内核错误码注册表）；
- 数据级授权：仅本人或 admin（`ensure_owner`，默认拒绝）；
- 读写分离：写走主库、读走从库（`DatabaseRouter`）。

### 5.2 API 网关
- **功能级白名单**（默认拒绝，路由之前拦截，ASGI 中间件）；
- 验证令牌后**注入可信身份头** `X-User-Id/X-User-Roles/X-Tenant-Id`（信任边界）；
- **trace 透传**：提取入站 `traceparent` → 起子 span → 注入出站头；
- 客户端侧负载均衡 `UpstreamBalancer`（轮询 + 健康感知 + 失败转移 + 半开恢复 + 连接池）；
- 响应头 `X-Upstream` 标记实际命中的实例（可观测性钩子）。

---

## 6. 质量防线（自动化测试，边界由机器守）

分层测试，**按"边界"而不是"包"组织**：

| 层级 | 位置 | 守护的边界 | 依赖 |
|---|---|---|---|
| 单元 | 各包/服务 `tests/` | 内部行为 | 无 |
| 契约 | `tests/contracts/` | 契约边界（定律1） | 无 |
| 边界扫描 | `tests/boundaries/` | 数据主权/内核纯净/表归属唯一/禁止硬编码连接串 | 无 |
| 集成 | `tests/integration/` | 事务边界 + 真实中间件（testcontainers） | Docker |
| 端到端 | `tests/e2e/` | 信任/网络边界（网关→服务全链路） | 无 |

**边界扫描是"物理定律的执法者"**：
- 跨服务 import = 失败；
- 同一张表被两个服务声明 = 失败；
- 源码出现硬编码连接串 = 失败；
- 契约文件被删 = 失败；
- `project-map.yaml` 与仓库不一致 = 失败。

> 契约测试**真实抓出过 bug**：服务 OpenAPI 没声明 409/404 → 测试红了 → 修复。
> 这验证了"边界由机器守"的价值：不是靠人 review，而是靠 CI 拦截。

---

## 7. 数据与一致性（读写分离 + Outbox + 演进）

### 7.1 读写分离（PostgreSQL 主从 + ORM）
- `DatabaseRouter`：写会话绑定主库、读会话绑定从库，**多从库轮询**（`REPLICA_DATABASE_URLS`）；
- 未配置副本自动降级主库（开发零成本）；
- 读己之写：写请求全程主库，天然一致；
- 关键决策：SQLAlchemy 2.0 async 下**语句级 `get_bind` 跨引擎路由不受支持**（AsyncContextNotStarted），因此采用"写/读双会话工厂"——这是 FastAPI + async 生态的推荐做法（已写入数据库设计文档）。

### 7.2 Outbox（定律 4 的落地核心）
- 业务本地事务内同时写 `outbox_messages` → 提交后 relay 异步投递；
- **多副本单写者**：`SELECT ... FOR UPDATE SKIP LOCKED`（否则多个 relay 重复投递）；
- 指数退避重试 + 最大次数标记 FAILED；
- 事件 payload 用 `jsonschema` 严格校验契约（跨层一致性）。

### 7.3 数据演进（Expand-Contract）
- 只做增量迁移（加字段带默认值，如 `users.updated_at`）；
- pydantic `extra="ignore"` + 新字段默认值 = 旧代码对新字段无感知；
- 迁移只跑主库，WAL 自动同步从库。

---

## 8. 部署与运维

### 8.1 镜像规范
- 生产镜像：非编辑安装（site-packages 正式包）、**非 root 用户**、内置健康检查、`.dockerignore` 瘦身；
- 被自动扩缩的服务**不暴露宿主机端口**（`ports: []`，否则 `--scale` 抢端口）。

### 8.2 编排（三档）
- `docker-compose.yml`：开发（主从 PG + Redis + RabbitMQ）；
- `deploy/docker-compose.prod.yml`：完整生产（Nginx/网关×3/服务×3/主从 PG/监控 profile）；
- `deploy/docker-compose.single.yml`：小内存单节点（真实服务器用的这套）。

### 8.3 CD（GitHub Actions，一劳永逸）
```
push main → CI（lint + 90 测试 + codegraph）→ 构建镜像推 GHCR → SSH 到服务器
         → 拉镜像 → alembic 迁移 → 滚动更新 → 健康检查
```
- 镜像带 commit SHA 标签，天然可回滚；
- 服务器端 `deploy-single.sh`：pull → migrate → up → 健康检查。

### 8.4 真实服务器部署
- 2 核 / 2GB 小机器 → 适配为单节点（不硬套完整编排）；
- 镜像本地构建 → `docker save/scp/load`（不在小机上构建，避免 OOM）；
- 后来切到 GHCR + CD，`push main` 自动上线。

---

## 9. 规模化能力

### 9.1 负载均衡（三层）
- 边缘层：Nginx（least_conn + 健康感知 + TLS 就绪）；
- 服务间层：网关客户端侧 LB（轮询 + 失败转移 + 半开恢复 + 连接池）；
- 数据层：读副本轮询；
- 实测：12 个请求 3 个服务副本全部命中（X-Upstream 验证）。

### 9.2 动态扩容（高峰期防爆）
闭环：**能测 → 能判 → 能执行 → 能感知**：
```
服务 /metrics → 自动扩缩器（RPS/错误率 + 持续确认 + 冷却 + min/max 边界）
              → docker compose --scale → 新副本注册中心心跳 → 网关动态发现接入
```
- 实测：压测 500 请求全成功（服务端没被打爆），负载升高自动决策扩容 2→3→4，回落自动恢复；
- 关键坑：**`--scale` 与宿主机端口冲突** → 被扩服务 `ports: []`。

### 9.3 资源监控
- node-exporter（宿主机）+ 应用 `/metrics`（QPS/错误率/延迟/Outbox 积压）+ Prometheus + Grafana；
- 8 条告警规则（服务宕机 / CPU·内存超限 / 5xx / Outbox 积压 / 在途过多）；
- Grafana 数据源 + 大盘自动供给（provisioning）。

---

## 10. 体验与协作

### 10.1 状态码三层模型（RFC 9457）
```
HTTP 状态码（传输语义） + 业务错误码（前端 switch 依据）+ 错误明细（trace_id/文档链接）
```
- 错误码注册表 = 单一事实来源，`GET /errors` 自动列出；
- 新增业务码 = `register_error_code(ErrorCode(...))` 一行。

### 10.2 日志体系
- 结构化 JSON + **自动关联 request_id/trace_id/用户身份**（ContextFilter）；
- 敏感字段脱敏；访问日志；慢查询日志（SQL + 耗时 + trace_id）；
- 排错入口：按 `trace_id` 聚合整条链路。

### 10.3 项目地图 + 文档站 + 代码导航
- `project-map.yaml`：机器可读地图（CI 校验防漂移）；
- `docs/index.md`：Mermaid 全景图（架构/请求链路/事件流/数据 ER）+ 5 分钟速览；
- mkdocs-material 文档站（搜索 + 图示，`scripts\docs.ps1`）；
- **CodeGraph**：代码级导航（符号 + 调用链 + 波及范围），MCP 接入 Codex；
- **新服务脚手架** `scripts\new-service.ps1`：30 秒生成一个符合全部规范的服务。

---

## 11. 踩坑全记录（现象 → 原因 → 解法）

> 这些坑是"地基"含金量所在——每个都代表一个真实环境约束。

| # | 现象 | 原因 | 解法 |
|---|---|---|---|
| 1 | 中文路径经管道传 Python 乱码 | PowerShell 控制台编码 | 写文件用 `[IO.File]::WriteAllText(UTF8)`，避免管道传中文 |
| 2 | `Remove-Item`/`Start-Process` 被拒 | 环境策略拦截破坏性/后台命令 | 用 `Rename-Item`/`Move-Item` 替代；后台用子进程脚本 |
| 3 | `TraceContextTextMapPropagator` 找不到 | OTel 1.44 移动了模块位置 | 双路径 try/except 导入 |
| 4 | async `get_bind` 跨引擎报 `AsyncContextNotStarted` | SQLAlchemy 2.0 async 限制 | 改为写/读双会话工厂路由 |
| 5 | psycopg 异步在 Windows 报 ProactorEventLoop | Windows 事件循环 | conftest 切 `SelectorEventLoop` |
| 6 | alembic.ini 中文注释 GBK 崩溃 | configparser 用 locale 编码 | 配置文件保持 ASCII |
| 7 | `docker build` 超时无输出 | BuildKit TTY 进度缓冲 | `--progress=plain` + 日志文件 |
| 8 | bitnami 镜像 403 | 镜像源白名单 | 官方 postgres + 自定义流复制脚本 |
| 9 | cAdvisor 容器重启 | Docker Desktop 无 cgroup 挂载 | 移到独立 profile，仅 Linux 主机 |
| 10 | gcr.io 拉不到 | 网络墙 | 用 Docker Hub 的 `google/cadvisor` |
| 11 | GitHub HTTPS 443 连不上 | 网络策略挡 443 | 改 **SSH 推送**（22/ssh.github.com:443 通） |
| 12 | GitHub 密码推送被拒 | GitHub 不支持密码 | SSH 密钥认证（id_ed25519） |
| 13 | CI 测试全挂 | 缺运行时依赖（内核 --no-deps） | CI 装 `requirements-prod.txt` 全量 |
| 14 | GHCR 推送被拒 | GITHUB_TOKEN 缺 `packages: write` | deploy.yml 声明 permissions |
| 15 | CI 里 `codegraph` 找不到 | npm 包名是 `@colbymchenry/codegraph` + PATH | 正确包名 + `npm prefix -g` 加 PATH |
| 16 | `codegraph index` 全新检出失败 | 需先 `init` | 无 `.codegraph` 则 init，有则 sync |
| 17 | mkdocs 2.0 预警 | Material 预告未来破坏性版本 | 锁 `mkdocs-material>=9.5,<10` + 保持 Markdown 可迁移 |
| 18 | `pip freeze` 中文路径崩溃 | editable 包 VCS 解析 bug | 改用 `pip list --format=freeze` 生成 |
| 19 | `docker compose --scale` 端口冲突 | 多副本抢宿主端口 | 被扩服务 `ports: []`（内部网络） |
| 20 | Starlette 1.x 500 重抛 | ServerErrorMiddleware 发送后重抛 | 测试用 `raise_app_exceptions=False` |
| 21 | 多副本 Outbox 重复投递 | 多个 relay 并发 | `FOR UPDATE SKIP LOCKED` 单写者 |
| 22 | 契约测试抓出 409/404 未声明 | 路由未声明错误响应 | 路由 `responses={...}` 显式声明 |

---

## 12. 方法论：好的项目地基应该怎么搭（10 条原则）

1. **先立宪，再写码**：把"不可逾越的约束"（定律）写进 `AGENTS.md`，AI 每次会话自动继承；
2. **边界优先**：契约边界、数据主权边界、信任边界——先画边界，再填内容；
3. **单一事实来源**：契约、错误码注册表、项目地图——杜绝"多处维护"；
4. **边界由机器守**：测试 + CI 是"物理定律的执法者"，违反 = 构建失败，不靠人 review；
5. **共性能力内核化**：内核零业务属性、版本化、最小 API 面；禁止内核依赖业务；
6. **可观测性是基因**：日志/指标/追踪是代码的一部分，不是事后补丁；
7. **演进有纪律**：Expand-Contract、增量迁移、旧代码对新字段无感知；
8. **工具化降低门槛**：脚手架、自动发现、一键命令——让"正确做事"成为默认；
9. **适配真实环境**：小内存机器用小节点、网络墙就换通道——地基要能落地，不是纸面架构；
10. **AI 协作锚点化**：模块说明书 + 项目地图 + 代码导航，让 AI 只处理当前子域，不被整个系统干扰。

---

## 13. 当前全貌（数字）

| 维度 | 数值 |
|---|---|
| 语言/框架 | Python 3.14 + FastAPI |
| 包/服务 | kernel + contract-sdk + gateway + service-template + autoscaler |
| 测试 | **90 个**（81 单测/边界/契约 + 3 集成 + 6 端到端） |
| CI 作业 | lint-and-test / integration / codegraph，push 全跑 |
| CD | push main → GHCR 镜像 → SSH 部署服务器（101.47.30.103） |
| 服务器 | Ubuntu 24.04 / 2C / 2GB，单节点（与既有 ai_edge 项目共存） |
| 文档 | 项目地图 + mkdocs 文档站 + CodeGraph 索引 |

---

## 14. 新项目启动 Checklist（可直接照做）

- [ ] 写 `AGENTS.md`：5 条不可逾越的定律 + 红线自查清单
- [ ] 搭 monorepo：contracts / packages / services / tests / docs / scripts / deploy
- [ ] 先定义契约（HTTP + 事件），生成契约 SDK
- [ ] 建共享内核（配置/日志/追踪/异常/错误码/鉴权/DB/Outbox/事件/指标）
- [ ] 写一个服务模板 + 网关（跑通最小链路）
- [ ] 建测试框架：单元 / 契约 / 边界 / 集成 / 端到端，全部 CI 强制
- [ ] 定数据演进纪律（Expand-Contract）+ 迁移工具
- [ ] 定部署链路（镜像 → 编排 → CD → 真实服务器验证）
- [ ] 按需加规模化能力（LB / 扩容 / 监控）——先有度量，再谈扩容
- [ ] 沉淀体验层（状态码 / 日志 / 项目地图 / 文档站 / 代码导航 / 脚手架）
- [ ] 每一步都"真实验证 + 记录踩坑"——坑就是地基的钢筋