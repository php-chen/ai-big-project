# ruff 静态检查
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
& (Join-Path $Root ".venv\Scripts\python.exe") -m ruff check packages services