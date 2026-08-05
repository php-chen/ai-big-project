# CodeGraph 代码索引助手（代码级导航：AI 与开发者共用）
# 用法:
#   scripts\codegraph.ps1 -Status                # 索引状态
#   scripts\codegraph.ps1 -Sync                  # 增量同步（拉取代码后执行）
#   scripts\codegraph.ps1 -Init                  # 首次初始化/重建索引
#   scripts\codegraph.ps1 -Explore "UserService" # 探索：相关符号源码 + 调用路径
#   scripts\codegraph.ps1 -Node "create_user"    # 单符号源码 + 调用/被调用
param(
    [switch]$Status,
    [switch]$Sync,
    [switch]$Init,
    [string]$Explore = "",
    [string]$Node = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command codegraph -ErrorAction SilentlyContinue)) {
    Write-Host "[codegraph] 未安装，请先: npm install -g codegraph"
    exit 1
}

if ($Init) { codegraph init }
elseif ($Sync) { codegraph sync }
elseif ($Explore) { codegraph explore $Explore }
elseif ($Node) { codegraph node $Node }
else { codegraph status }