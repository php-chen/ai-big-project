# 一键初始化：创建虚拟环境 + 安装全部依赖
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] 创建虚拟环境 (Python 3.14) ..."
    py -3.14 -m venv .venv
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "[setup] 安装可编辑包 ..."
& $Py -m pip install --no-input -e packages/contract-sdk
& $Py -m pip install --no-input --no-deps -e packages/kernel
& $Py -m pip install --no-input --no-deps -e services/service-template
& $Py -m pip install --no-input --no-deps -e services/gateway

Write-Host "[setup] 安装开发依赖 ..."
& $Py -m pip install --no-input pytest pytest-asyncio ruff aiosqlite alembic

Write-Host "[setup] 完成。启动中间件: docker compose up -d"