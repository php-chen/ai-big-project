# 新服务脚手架：基于 service-template 复制出 services/<Name>，并自动登记到
#   边界扫描(conftest SERVICE_PACKAGES)、项目地图(project-map.yaml)、数据归属矩阵、模块说明书
# 用法: scripts\new-service.ps1 -Name orders [-Port 8200]
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [int]$Port = 8200
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "services\service-template"
$Dst = Join-Path $Root "services\$Name"
$Pkg = "$Name`_app"

if (-not (Test-Path $Src)) { throw "找不到模板: $Src" }
if (Test-Path $Dst) { throw "已存在: $Dst" }

function Read-Utf8([string]$p) { return [System.IO.File]::ReadAllText($p) }
function Write-Utf8([string]$p, [string]$c) { [System.IO.File]::WriteAllText($p, $c, (New-Object System.Text.UTF8Encoding($false))) }

Write-Host "==> 复制模板 -> services\$Name"
Copy-Item -Recurse $Src $Dst
Rename-Item (Join-Path $Dst "app") $Pkg

Write-Host "==> 重命名包 app -> $Pkg 及全局引用"
Get-ChildItem $Dst -Recurse -File -Include *.py,*.toml,*.md,*.ini,*.yaml,*.yml,*.env.example,Dockerfile,*.mako | ForEach-Object {
    $c = Read-Utf8 $_.FullName
    $c = $c.Replace("app.main:app", "$Pkg.main:app")
    $c = $c.Replace("from app.", "from $Pkg.")
    $c = $c.Replace("from app import", "from $Pkg import")
    $c = $c.Replace('"app*"', '"' + $Pkg + '*"')
    $c = $c.Replace("service-template", $Name)
    Write-Utf8 $_.FullName $c
}

Write-Host "==> 设置端口 $Port"
$cfgPath = Join-Path $Dst "$Pkg\config.py"
$cfg = Read-Utf8 $cfgPath
$cfg = $cfg.Replace("    port: int = 8100   # 覆盖内核默认 8000（与编排一致）", "    port: int = $Port   # 覆盖内核默认 8000（与编排一致）")
$cfg = $cfg.Replace("port: int = 8100", "port: int = $Port")
Write-Utf8 $cfgPath $cfg

Write-Host "==> 登记边界扫描 SERVICE_PACKAGES"
$ct = Join-Path $Root "tests\conftest.py"
$c = Read-Utf8 $ct
$anchor = '    "gateway_app": "gateway",         # 网关的包名 -> 服务目录'
if ($c.Contains($anchor)) {
    $c = $c.Replace($anchor, $anchor + "`n" + "    `"$Pkg`": `"$Name`",             # $Name 的包名 -> 服务目录")
    Write-Utf8 $ct $c
}

Write-Host "==> 登记项目地图 project-map.yaml"
$pm = Join-Path $Root "project-map.yaml"
$p = Read-Utf8 $pm
$entry = "  $Name`:`n    path: services/$Name`n    package: $Pkg`n    port: $Port`n    replicas: 1`n    description: $Name 服务（新建，待完善模块说明书）`n    envs: [DATABASE_URL, REDIS_URL]`n    depends_on: []`n    owns_tables: []`n    publishes: []`n    subscribes: []`n`n"
$p = $p.Replace("middleware:", $entry + "middleware:")
Write-Utf8 $pm $p

Write-Host "==> 登记数据归属矩阵"
$om = Join-Path $Root "docs\architecture\02-ownership-matrix.md"
$o = Read-Utf8 $om
$row = "| $Name（待建） | - | user_id 等 | - | - |"
$o = $o.Replace("## 反例速查", $row + "`n`n## 反例速查")
Write-Utf8 $om $o

Write-Host "==> 生成模块说明书"
$specSrc = Join-Path $Root "docs\module-specs\template.md"
$specDst = Join-Path $Root "docs\module-specs\$Name.md"
$s = Read-Utf8 $specSrc
$s = $s.Replace("<服务名>", $Name)
Write-Utf8 $specDst $s

Write-Host ""
Write-Host "✅ 新服务已创建: services\$Name（包 $Pkg，端口 $Port）"
Write-Host ""
Write-Host "下一步："
Write-Host "  1. 在 contracts/http/ 定义 $Name 的 API 契约（先写契约！）"
Write-Host "  2. 在 contracts/events/ 定义事件 schema"
Write-Host "  3. 完善 docs/module-specs/$Name.md（六要素）"
Write-Host "  4. 实现业务代码（只引用契约 SDK 与内核，只访问自己的表）"
Write-Host "  5. scripts\test.ps1 + scripts\lint.ps1 通过后提交"