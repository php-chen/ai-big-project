# 启动服务模板（热重载，端口 8100）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "services\service-template")
& (Join-Path $Root ".venv\Scripts\python.exe") -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8100