# 本地构建生产镜像（供 deploy/docker-compose.prod.yml 使用）
# 用法：scripts\docker-build.ps1 [-Tag dev] [-Registry ai-big]
param([string]$Tag = "dev", [string]$Registry = "ai-big")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker build --progress=plain -f services/service-template/Dockerfile -t "$Registry/service-template:$Tag" .
if ($LASTEXITCODE -ne 0) { exit 1 }

docker build --progress=plain -f services/gateway/Dockerfile -t "$Registry/gateway:$Tag" .
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "镜像构建完成：$Registry/service-template:$Tag 与 $Registry/gateway:$Tag"
Write-Host "全栈启动：docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d"