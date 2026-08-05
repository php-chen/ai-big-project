#!/bin/bash
# 服务器端部署验证脚本（ASCII，避免引号问题）
set -u
cd /root/ai-big/deploy

echo "===== 容器状态 ====="
docker compose -f docker-compose.single.yml ps --format "table {{.Name}}\t{{.Status}}"

echo ""
echo "===== 网关健康 ====="
curl -s -o /dev/null -w "gateway /health/live -> %{http_code}\n" http://localhost:8000/health/live

echo "===== 模板就绪（含 db 检查）====="
curl -s http://localhost:8100/health/ready
echo ""

echo "===== 经网关创建用户 ====="
CREATE=$(curl -s -X POST http://localhost:8000/v1/users \
  -H 'Authorization: Bearer dev-token' \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: deploy-1' \
  -d '{"email":"deploy@server.dev","display_name":"Deploy"}')
echo "$CREATE"

ID=$(echo "$CREATE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -n "$ID" ]; then
  echo ""
  echo "===== 经网关查询用户（$ID）====="
  curl -s http://localhost:8000/v1/users/$ID -H 'Authorization: Bearer dev-token'
  echo ""
fi

echo ""
echo "===== 错误码清单（前 200 字符）====="
curl -s http://localhost:8100/errors | head -c 200
echo ""