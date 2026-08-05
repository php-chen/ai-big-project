# <服务名> · 模块说明书

> 复制本模板到 `docs/module-specs/<service>.md`，逐项填写。六要素缺一不可。

## 1. 服务职责

<!-- 一句话说清：本服务负责什么、不负责什么 -->

## 2. API 契约

- 契约文件：`contracts/http/<service>.openapi.yaml`
- 契约 SDK：`contract_sdk/schemas/<domain>.py`
- 错误格式：RFC 9457（见 docs/standards/response-and-errors.md）

## 3. 核心表 ER

<!-- Mermaid erDiagram：本服务拥有的全部表 + 关键字段（含默认值标注） -->

## 4. 数据归属边界

| 拥有 | 只引用 ID | 严禁访问 |
|---|---|---|
| （表名） | （其他服务 `*_id`） | （其他服务的任何表） |

## 5. 事件

| 方向 | 事件 | 契约文件 |
|---|---|---|
| 发布 | `<domain>.<action>.v1` | `contracts/events/<event>.schema.json` |
| 订阅 | （Read Model 事件） | ... |

## 6. 非功能要求与完成定义

- [ ] 副作用接口支持 Idempotency-Key
- [ ] 本地事务 + Outbox（禁止提交前直发 MQ）
- [ ] 数据级授权默认拒绝
- [ ] 结构化日志带 request_id/trace_id；trace 透传
- [ ] /health/live + /health/ready
- [ ] 契约与归属矩阵已登记
- [ ] 测试通过（scripts/test.ps1）