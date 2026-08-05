# 契约层（Contract-First 唯一事实来源）

本目录是**所有接口与事件的唯一事实来源**，业务代码只能引用由契约生成/镜像的 SDK 类型。

## 目录

```
contracts/
  http/*.openapi.yaml     # HTTP 接口契约（OpenAPI 3.1）
  events/*.schema.json    # 领域事件消息体（JSON Schema 2020-12）
```

## 演进规则（不可违反）

1. **增量优先**：新增字段必须带默认值（`default` / `nullable`），禁止删改已有必填字段。
2. **破坏性变更必须升版本**：HTTP 用路径/版本头；事件名带版本后缀（`user.created.v1` → `user.created.v2`），旧版本在兼容窗口内继续被消费。
3. **契约即代码**：`contract-sdk` 中的 pydantic 模型由本目录生成（CI 中用 `datamodel-code-generator`），禁止手改后不同步。
4. **禁止在业务代码中临时捏造字段**。任何新字段，先改契约，再改代码。

## 校验工具

- HTTP 契约 → OpenAPI（FastAPI 可在测试中校验响应符合契约）
- 事件契约 → JSON Schema 校验（`jsonschema`）