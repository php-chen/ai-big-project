# 数据库设计（PostgreSQL + SQLAlchemy 2.0 async · 读写分离）

## 1. 表设计

### users（用户服务拥有）
| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | varchar(36) | PK | UUID |
| email | varchar(255) | UNIQUE + index | 登录标识 |
| display_name | varchar(64) | NOT NULL | |
| status | varchar(16) | default `active` | active/disabled |
| created_at | timestamptz | default `now()` | |
| vip_level | int | default `0` | 演进示例（迁移 0001） |
| updated_at | timestamptz | default `now()` | 演进示例（迁移 0002，onupdate） |

### outbox_messages（事务发件箱，定律4）
| 字段 | 类型 | 约束/默认 | 说明 |
|---|---|---|---|
| id | varchar(36) | PK | 事件 ID（= event_id） |
| event_name | varchar(128) | index | 如 `user.created.v1` |
| aggregate_type / aggregate_id | varchar | index | 聚合定位 |
| payload | jsonb | NOT NULL | 事件消息体（契约校验） |
| headers | jsonb | NOT NULL | trace 上下文等 |
| status | varchar(16) | index, default `pending` | pending/sent/failed |
| attempts | int | default `0` | 重试计数（指数退避） |
| next_attempt_at / created_at / sent_at | timestamptz | | 投递调度 |

## 2. 读写分离架构

```
                     ┌─────────────┐
  写请求 ───────────> │  主库 primary │ <── WAL 流复制 ──┐
  (create/update)    └─────────────┘                   │
                                                       ▼
  读请求 ───────────>  ┌──────────────┐        ┌─────────────────┐
  (get/list)          │ DatabaseRouter│ 绑定   │ 从库 replica     │
                      │  write_factory│ ─────> │ (只读, 接受副本滞后)│
                      │  read_factory │ ─────> └─────────────────┘
                      └──────────────┘
```

### 路由规则（kernel/db.py 的 DatabaseRouter）
- **写会话** `write_factory`：绑定主库。写 + **读己之写**（会话内刚写的数据立刻能读到）天然保证。
- **读会话** `read_factory`：绑定从库。纯读请求走副本，降低主库压力。
- **未配置 `REPLICA_DATABASE_URL`**：从库自动降级为主库（开发/测试零成本）。
- 实现说明：SQLAlchemy 2.0 async 下**语句级 get_bind 跨引擎切换不受支持**（AsyncContextNotStarted，SQLAlchemy 已知限制），因此采用“写/读双会话工厂”路由——这也是 FastAPI + async SQLAlchemy 生产推荐做法。

### 一致性语义
- 单请求内：写请求全程主库（读己之写 ✅）；读请求全程从库。
- 跨请求：从库可能滞后（毫秒~秒级），**接受最终一致性**；对一致性要求高的读（如支付前校验），用写会话/显式主库读。
- 强制主库读：`async with db.write_factory() as s: ...`。

## 3. 索引策略
- 唯一索引：`users.email`（业务幂等）；`outbox_messages.id`（PK）。
- 高频查询索引：`outbox_messages.status + created_at`（relay 扫描 pending）。
- 外键：**不建物理外键**（微服务数据主权，跨服务只存 ID，约束在服务层）。

## 4. 演进规范（方向三 Expand-Contract）
- 只允许增量迁移（加字段带默认值，如迁移 0001/0002）；
- 迁移只跑主库，WAL 自动同步到从库（**从库永远不手动迁移**）；
- pydantic 模型 `extra="ignore"` + 新字段带默认值（旧代码无感知）；
- 破坏性变更必须走完整 Expand-Contract 五步（见 docs/standards/expand-contract.md）。

## 5. 健康检查
- `/health/ready` 返回 `db_write`（主库）与 `db_read`（从库）两项探测结果；
- 任一下游不可用 => 503，编排据此触发告警/重启。

## 6. 注意事项
- Outbox Relay 是“写完立刻读”的循环，**必须使用写会话**（主库），避免副本滞后漏投事件。
- 从库连接串与主库分离（`REPLICA_DATABASE_URL`），禁止在代码中硬编码。
- 生产从库通过流复制同步 schema；扩容副本 = 编排加一台 `postgres-replica`（Bitnami slave 模式）。