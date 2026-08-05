# 自动化测试框架（微服务边界导向）

> 微服务自动化测试的核心不是“测了多少代码”，而是**守住每条边界**。
> 本框架按“边界”而不是“包”组织测试，让任何一条定律被违反时，CI 立刻变红。

## 测试分层（金字塔）

| 层级 | 位置 | 覆盖的边界 | 依赖 |
|---|---|---|---|
| 单元测试 | 各包/服务 `tests/` | 服务内部行为 | 无（sqlite 内存） |
| 契约测试 | `tests/contracts/` | **契约边界**（定律1） | 无 |
| 边界扫描 | `tests/boundaries/` | **代码结构边界**（定律2/方向一/二） | 无 |
| 集成测试 | `tests/integration/` | **事务边界 + 中间件**（定律4） | Docker（testcontainers） |
| 端到端 | `tests/e2e/` | **网络/信任边界**（定律3/5） | 无（自动起子进程） |

## 各边界怎么测

### 契约边界（定律1）
- `test_event_schema.py`：contract_sdk 镜像模型输出、以及**服务实际写入 outbox 的 payload**，都用 `jsonschema` 严格校验 `contracts/events/*.json`。契约改 schema 而服务不改 → 立刻失败。
- `test_http_contract.py`：服务 `app.openapi()` 必须覆盖契约 OpenAPI 的每个 path+method+响应码（契约 ⊆ 实现）。

### 数据主权边界（定律2）
- `test_data_sovereignty.py`：
  - 服务之间禁止相互 import（红线）；
  - 任何表名只能有一个 Owner（扫描 `__tablename__` 求交集）；
  - 网关零数据访问（禁止 import sqlalchemy/kernel.db）。

### 内核纯度边界（方向二）
- `test_kernel_purity.py`：内核禁止 import 任何服务包；只允许依赖契约层。

### 环境标准化边界（方向一）
- `test_no_hardcoded_config.py`：源码中禁止出现生产连接串（postgres/mysql/redis/amqp/mongodb）。

### 事务边界（定律4，集成）
- `test_outbox_event_flow.py`（testcontainers 拉起真实 PostgreSQL/Redis/RabbitMQ）：
  - 创建用户 → 本地事务 + outbox 同事务落库；
  - OutboxRelay 投递到 RabbitMQ → EventConsumer 收到且 payload 符合契约；
  - Redis 幂等存储语义（acquire/put/get）；
  - 真实库上的唯一约束冲突（409）。

### 信任/网络边界（定律3/5，端到端）
- `test_gateway_flow.py`（自动启动 uvicorn 子进程）：
  - 无 token → 401；白名单外 → 403；
  - 经网关创建 → 201（身份注入 + trace 透传）；
  - 本人 200 / 他人 403 / admin 200；
  - 同一 Idempotency-Key 重复请求只执行一次；
  - 响应回写 X-Request-ID（定律5）。

## 运行方式

```powershell
scripts\test.ps1                # unit（默认）：各包单测 + 边界扫描 + 契约
scripts\test.ps1 -Level contract
scripts\test.ps1 -Level integration   # 需要 Docker，无则自动跳过
scripts\test.ps1 -Level e2e
scripts\test.ps1 -Level all
scripts\coverage.ps1            # 覆盖率报告（可选 -FailUnder 60 门槛）
```

CI（`.github/workflows/ci.yml`）：push/PR 跑 lint + unit + boundary + contract + e2e；push 时追加 integration（GitHub Actions 自带 Docker）。

## 新增边界测试的约定

1. 新增一个业务事件 → 在 `test_event_schema.py` 的 `SAMPLE_BUILDERS` 登记样例构造器；
2. 新增一个服务 → 更新 `tests/conftest.py` 的 `SERVICE_PACKAGES` 映射，边界扫描自动覆盖；
3. 新增一张表 → 表归属唯一性测试自动校验（无需改测试）。