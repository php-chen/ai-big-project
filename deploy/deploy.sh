#!/usr/bin/env bash
# 服务器侧部署脚本：拉取镜像 -> 数据库迁移 -> 滚动更新 -> 健康检查
# 用法：TAG=<commit-sha> ./deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)
TAG="${TAG:-latest}"

echo "==> 拉取镜像 (TAG=$TAG)"
"${COMPOSE[@]}" pull

echo "==> 数据库迁移（alembic upgrade head）"
"${COMPOSE[@]}" run --rm migrate

echo "==> 滚动更新服务（service-template / gateway）"
"${COMPOSE[@]}" up -d --no-deps service-template gateway

echo "==> 健康检查"
sleep 8
"${COMPOSE[@]}" ps