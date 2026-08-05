# 数据归属矩阵（数据主权，定律2）

> 原则：每张表有且只有一个 Owner；跨服务只引用 ID；Read Model 走事件。
> 新增服务/表时，必须在本表登记。

## 当前矩阵

| 服务 | 拥有（唯一 Owner） | 只引用 ID | 订阅事件（Read Model） | 发布事件 |
|---|---|---|---|---|
| service-template（用户服务原型） | users、outbox_messages | 其他服务 `*_id` | order.created.v1（示例） | user.created.v1 |
| gateway | 无（零数据访问） | - | - | - |
| 订单服务（待建） | orders、outbox_messages | user_id、product_id | user.created.v1 | order.created.v1 |
| 资料服务（待建） | profiles、outbox_messages | user_id | user.created.v1 | profile.updated.v1 |

## 反例速查

- ❌ 订单服务存 `users.email`（应存 `user_id`，展示时聚合/读模型）
- ❌ 资料服务直接改 `users` 表（users 只归用户服务）
- ✅ 资料服务订阅 `user.created.v1` 建 profile 初始化行（Read Model）

## 冲突裁决

- 两个服务都想拥有同一张表 -> 上报项目负责人裁决，禁止自行复制权威字段。