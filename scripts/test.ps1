# 分层自动测试入口
# 用法:
#   scripts\test.ps1                      # 默认 unit
#   scripts\test.ps1 -Level contract      # 契约测试
#   scripts\test.ps1 -Level integration   # 集成测试（需要 Docker）
#   scripts\test.ps1 -Level e2e           # 端到端测试（自动起子进程）
#   scripts\test.ps1 -Level all           # 全部
param(
    [ValidateSet("unit", "contract", "integration", "e2e", "all")]
    [string]$Level = "unit"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Failed = $false

function Run-Pytest([string]$Name, [string[]]$ArgsList) {
    Write-Host ""
    Write-Host "==== $Name ===="
    Push-Location $Root
    & $Py -m pytest @ArgsList -q
    if ($LASTEXITCODE -ne 0) { $Failed = $true }
    Pop-Location
}

# 自动发现所有包与服务（新增模块无需改本脚本）
$UnitDirs = @("packages\contract-sdk", "packages\kernel")
$UnitDirs += Get-ChildItem (Join-Path $Root "services") -Directory | ForEach-Object { "services\$($_.Name)" }
$UnitDirs += Get-ChildItem (Join-Path $Root "packages") -Directory | Where-Object { $_.Name -ne "contract-sdk" -and $_.Name -ne "kernel" } | ForEach-Object { "packages\$($_.Name)" }

switch ($Level) {
    "unit" {
        foreach ($Dir in $UnitDirs) {
            Write-Host ""
            Write-Host "==== pytest $Dir (unit) ===="
            Push-Location (Join-Path $Root $Dir)
            & $Py -m pytest -m "not integration and not e2e" -q
            if ($LASTEXITCODE -ne 0) { $Failed = $true }
            Pop-Location
        }
        Run-Pytest "根级 边界扫描 + 契约测试" @("tests/boundaries", "tests/contracts", "-m", "not integration and not e2e")
    }
    "contract" {
        Run-Pytest "契约测试（事件 schema + HTTP 覆盖）" @("tests/contracts", "-m", "not integration and not e2e")
    }
    "integration" {
        Run-Pytest "集成测试（真实中间件，需要 Docker）" @("tests/integration", "-m", "integration")
    }
    "e2e" {
        Run-Pytest "端到端测试（网关 -> 服务）" @("tests/e2e", "-m", "e2e")
    }
    "all" {
        foreach ($Dir in $UnitDirs) {
            Write-Host ""
            Write-Host "==== pytest $Dir (unit) ===="
            Push-Location (Join-Path $Root $Dir)
            & $Py -m pytest -m "not integration and not e2e" -q
            if ($LASTEXITCODE -ne 0) { $Failed = $true }
            Pop-Location
        }
        Run-Pytest "根级 边界扫描 + 契约测试" @("tests", "-m", "not integration and not e2e")
        Run-Pytest "集成测试（需要 Docker，无则跳过）" @("tests/integration", "-m", "integration")
        Run-Pytest "端到端测试" @("tests/e2e", "-m", "e2e")
    }
}

if ($Failed) { Write-Host ""; Write-Host "!! 存在失败的测试"; exit 1 }
Write-Host ""
Write-Host "== 全部测试通过 =="