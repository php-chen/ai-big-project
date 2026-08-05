# 生成部署专用 SSH 密钥对（用于自动化部署）
# 用法: scripts\gen-deploy-key.ps1
# 提示输入 passphrase 时直接按两次回车（无口令，供自动化使用）
$ErrorActionPreference = "Stop"
$KeyPath = Join-Path $env:USERPROFILE ".ssh\ai-big-deploy"
if (Test-Path $KeyPath) {
    Write-Host "密钥已存在: $KeyPath（如需重建请先手动删除后再运行）"
} else {
    ssh-keygen -t ed25519 -f $KeyPath -C "ai-big-project deploy key"
    if ($LASTEXITCODE -ne 0) { throw "ssh-keygen 失败" }
    Write-Host "已生成: $KeyPath"
}
Write-Host ""
Write-Host "===== 公钥（复制到服务器的 ~/.ssh/authorized_keys）====="
Get-Content "$KeyPath.pub"