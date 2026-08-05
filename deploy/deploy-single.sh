#!/usr/bin/env bash
# 服务器侧部署脚本（精简单节点：适配小内存服务器）
# 用法：TAG=<commit-sha> REGISTRY=ghcr.io/<owner>/<repo> ./deploy-single.sh
# 流程：拉取 GHCR 镜像 -> 数据库迁移 -> 滚动更新服务 -> 健康检查
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.single.yml)
TAG="${TAG:-latest}"
REGISTRY="${REGISTRY:-ghcr.io/yourorg/ai-big-project}"

echo "==> 拉取镜像 (${REGISTRY}/service-template:${TAG})"
REGISTRY="$REGISTRY" TAG="$TAG" "${COMPOSE[@]}" pull

echo "==> 数据库迁移（alembic upgrade head）"
REGISTRY="$REGISTRY" TAG="$TAG" "${COMPOSE[@]}" run --rm migrate

echo "==> 滚动更新服务"
REGISTRY="$REGISTRY" TAG="$TAG" "${COMPOSE[@]}" up -d --no-deps service-template gateway

echo "==> 健康检查"
sleep 8
curl -s -o /dev/null -w "gateway /health/live -> %{http_code}\n" http://localhost:8000/health/live || true
"${COMPOSE[@]}" ps --format "table {{.Name}}\t{{.Status}}"