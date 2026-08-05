# 覆盖率统计（单元 + 契约 + 边界）
# 用法: scripts\coverage.ps1 [-FailUnder 60]
param([double]$FailUnder = 0)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

Push-Location $Root
& $Py -m pytest tests packages/kernel/tests packages/contract-sdk/tests services/service-template/tests services/gateway/tests `
    -m "not integration and not e2e" -q `
    --cov=kernel --cov=contract_sdk --cov=app --cov=gateway_app `
    --cov-report=term-missing --cov-fail-under=$FailUnder
Pop-Location