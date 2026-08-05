# 自动化部署

基于项目特点（微服务 monorepo、5 条物理定律、零停机演进、可观测性）的部署方案。

## 架构

```
  客户端 ──> Nginx(:80) 边缘LB ──> gateway ×3 (功能白名单/身份注入/trace)
              │
              └─ 客户端侧LB（轮询+健康感知）──> service-template ×3
              │
              └─ PostgreSQL 主库(写) ──WAL──> 从库(读, 轮询) / Redis / RabbitMQ
```

## 目录

| 文件 | 作用 |
|---|---|
| `docker-compose.prod.yml` | 生产编排（中间件 + 迁移 + 服务 + 可选 OTel） |
| `.env.prod.example` | 生产环境变量模板（复制为 `.env.prod`，禁止提交真实值） |
| `otel-collector.yaml` | OTel Collector 配置（定律5） |
| `deploy.sh` | 服务器侧部署脚本：pull → migrate → 滚动更新 → 健康检查 |

## 部署流程（零停机，符合 Expand-Contract 哲学）

```
1. 代码合并到 main -> GitHub Actions：
   - CI 全绿（unit + contract + boundary + e2e；integration 在 push 时）
   - 构建 gateway / service-template 镜像 -> 推送 GHCR（sha 标签 + latest）
2. SSH 到服务器执行 deploy.sh：
   - docker compose pull            （拉取新镜像）
   - docker compose run --rm migrate （先跑 Alembic 迁移，只做增量变更）
   - docker compose up -d --no-deps  （滚动更新服务，依赖健康检查）
   - 健康检查 /health/ready 通过后流量切换
3. 回滚：TAG=<上一版本 sha> ./deploy.sh
```

## 本地全栈预演

```powershell
# 1. 构建镜像（本地 tag）
scripts\docker-build.ps1 -Tag dev -Registry ai-big

# 2. 准备环境变量
Copy-Item deploy\.env.prod.example deploy\.env.prod   # 按需修改

# 3. 全栈启动（REGISTRY/TAG 指到本地镜像）
$env:REGISTRY="ai-big"; $env:TAG="dev"
docker compose -f deploy/docker-compose.prod.yml --env-file deploy\.env.prod up -d

# 4. 验证
Invoke-RestMethod http://localhost:8000/health/live
# 可选启用可观测性：加 --profile observability
```

## 生产清单（上生产前必须确认）

- [ ] `.env.prod` 中所有 `CHANGE_ME` 已替换为强密码/密钥
- [ ] 网关鉴权接入真实 JWT（`DEV_TOKEN` 仅用于预演）
- [ ] 网关与服务间启用 mTLS 或服务网格（`TRUST_PROXY_HEADERS=true` 的前提）
- [ ] `OTEL_EXPORTER_OTLP_ENDPOINT` 指向真实后端，`otel-collector.yaml` 的 exporter 已接 Jaeger/Tempo
- [ ] 数据库备份与恢复演练
- [ ] 从库 postgres-replica 流复制正常（/health/ready 中 db_read=ok）；POSTGRES_REPLICATION_PASSWORD 与 postgres/init-repl.sql 一致
- [ ] 镜像仓库（GHCR）权限与 `DEPLOY_HOST/DEPLOY_USER/DEPLOY_KEY` 已配置到 GitHub Secrets
- [ ] 日志采集（结构化 JSON -> 日志系统）

## 回滚

```bash
# 在服务器上回滚到上一版本
TAG=<上一版本 sha> ./deploy.sh
```