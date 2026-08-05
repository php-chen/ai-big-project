# 压测脚本：向目标地址持续发送请求（模拟高峰流量，供动态扩缩器观察）
# 用法: scripts\load-gen.ps1 [-Url http://localhost:18080/v1/users] [-Duration 60] [-Rps 30]
param(
    [string]$Url = "http://localhost:18080/v1/users",
    [int]$Duration = 60,
    [int]$Rps = 30
)
$ErrorActionPreference = "Stop"
$headers = @{ Authorization = "Bearer dev-token" }
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$sent = 0
$ok = 0
$fail = 0

Write-Host "压测开始: $Url | ${Rps} rps | ${Duration}s"
while ($stopwatch.Elapsed.TotalSeconds -lt $Duration) {
    $tasks = for ($i = 0; $i -lt $Rps; $i++) {
        $n = Get-Random
        $body = @{ email = "load$n@test.dev"; display_name = "Load$n" } | ConvertTo-Json
        try {
            $resp = Invoke-WebRequest -Method Post -Uri $Url -Body $body -ContentType "application/json" -Headers $headers -UseBasicParsing -TimeoutSec 10
            if ($resp.StatusCode -eq 201) { $script:ok++ } else { $script:fail++ }
        } catch {
            $script:fail++
        }
        $script:sent++
    }
    Start-Sleep -Milliseconds 1000
}
Write-Host "压测结束: sent=$sent ok=$ok fail=$fail"