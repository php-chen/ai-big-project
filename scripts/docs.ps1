# 文档站（项目地图）
# 用法:
#   scripts\docs.ps1 -Build    # 构建静态站点到 site/
#   scripts\docs.ps1 -Serve    # 本地预览 http://localhost:8000
param(
    [switch]$Serve,
    [switch]$Build
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path (Join-Path $Root ".venv\Lib\site-packages\mkdocs"))) {
    Write-Host "[docs] 首次使用，安装 mkdocs-material ..."
    & $Py -m pip install --no-input -r (Join-Path $Root "requirements-docs.txt")
}

if ($Serve) {
    Push-Location $Root
    & $Py -m mkdocs serve
    Pop-Location
} else {
    Push-Location $Root
    & $Py -m mkdocs build --strict
    Pop-Location
}