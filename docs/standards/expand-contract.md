# 数据演进零停机规范（方向三：Expand-Contract）

> 原则：**所有对表的增删字段，都必须带默认值，且旧代码对新字段无感知。**

## 五步流程（数据库变更）

```
1. 加列（可空 / 带默认值）        -- Expand
2. 双写双读（新旧代码并行）       -- 兼容期
3. 回填数据（后台任务）           -- Backfill
4. 收紧约束（必填/索引）          -- Contract
5. 清理旧列 / 旧代码             -- Remove
```

- 每一步可独立发布、可回滚；
- **禁止**一步到位：加必填列 / 删列 / 改列类型必须走完整流程。

## 代码级约定

- SQLAlchemy 模型：新字段 Python 侧 `default=` + DB 侧 `server_default=`；
- pydantic 模型：`model_config = ConfigDict(extra="ignore")`，新字段带默认值；
- 查询**显式列名**，禁止 `select *`（防新增列破坏旧逻辑）；
- 契约层：新字段必须 `default` 且为可选（见 contracts/README.md）。

## 反例

- ❌ 在已有表上加 `NOT NULL` 无默认值的列（存量行直接失败）；
- ❌ 删除字段后旧代码还在读（先删代码，再删列）；
- ❌ 反序列化遇到未知字段抛异常（应 `extra="ignore"`）。