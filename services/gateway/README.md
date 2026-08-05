# API 网关 · 模块说明书

## 1. 服务职责

- **功能级鉴权（定律3）**：只校验“能不能访问这个 URL”（白名单 + 角色），**不做数据级校验**。
- **身份注入**：验证令牌后注入可信头 `X-User-Id / X-User-Roles / X-Tenant-Id` 给下游。
- **trace 透传（定律5）**：提取入站 `traceparent` -> 起子 span -> 注入出站头。
- **反向代理**：把 `/v1/*` 转发到下游服务（`UPSTREAM_SERVICE_URL`）。

## 2. 功能白名单

登记在 `gateway_app/routes.py` 的 `ROUTE_WHITELIST`。**默认拒绝**：未登记的功能一律 403。
新增下游功能时，必须同时：更新契约 -> 登记白名单 -> 更新本文档。

| 方法 | 路径 | 角色 |
|---|---|---|
| POST | /v1/users | user, admin |
| GET | /v1/users/{user_id} | user, admin |

## 3. 边界

- 网关**不做**数据聚合（防 God Object）；聚合交给 BFF / 事件读模型。
- 网关**不碰**业务数据库（零数据访问）。

## 4. 本地运行

```powershell
scripts\gateway.ps1   # uvicorn gateway_app.main:app --reload --port 8000
```