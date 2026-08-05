# 契约 SDK（ai-contract-sdk）

由 `contracts/` 生成的线上报文类型（pydantic），是契约层的代码镜像。

## 内容

- `contract_sdk/events.py` —— 事件信封 `EventEnvelope` / `TraceContext`（所有领域事件的统一线上包装）
- `contract_sdk/schemas/` —— 各域 schema（HTTP DTO + 事件 payload）

## 与契约层的关系

```
contracts/*.openapi.yaml ──┐
                           ├──> datamodel-code-generator ──> contract_sdk/schemas/
contracts/events/*.json ───┘
```

## 生成命令（CI 中执行）

```bash
datamodel-code-generator --input contracts/http/template.openapi.yaml \
  --output packages/contract-sdk/contract_sdk/schemas/http.py \
  --input-file-type openapi
```

## 演进规则

- 新增字段：先改 `contracts/`，再重新生成；字段必须带默认值。
- 破坏性变更：事件升版本（`user.created.v1` → `.v2`），HTTP 走版本化。
- 禁止手改生成文件后不同步契约。