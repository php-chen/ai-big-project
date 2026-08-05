# 启动 API 网关（端口 8000）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "services\gateway")
& (Join-Path $Root ".venv\Scripts\python.exe") -m uvicorn gateway_app.main:app --reload --host 0.0.0.0 --port 8000