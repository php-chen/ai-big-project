#!/bin/bash
# 服务器端部署验证脚本（ASCII）
set -u
cd /root/ai-big/deploy

echo "===== 容器与镜像 ====="
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"

echo ""
echo "===== 网关健康 ====="
curl -s -o /dev/null -w "gateway /health/live -> %{http_code}\n" http://localhost:8000/health/live

echo "===== 模板就绪 ====="
curl -s http://localhost:8100/health/ready
echo ""

echo "===== 经网关创建用户 ====="
CREATE=$(curl -s -X POST http://localhost:8000/v1/users \
  -H 'Authorization: Bearer dev-token' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: cd-verify-1' \
  -d '{"email":"cd@server.dev","display_name":"CD"}')
echo "$CREATE"

ID=$(echo "$CREATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -n "$ID" ]; then
  echo ""
  echo "===== 经网关查询用户 ====="
  curl -s http://localhost:8000/v1/users/$ID -H 'Authorization: Bearer dev-token'
  echo ""
fi