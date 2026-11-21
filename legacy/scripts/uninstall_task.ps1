# 删除“青鸾项目每日导出”计划任务
param([string]$TaskName = "青鸾项目每日导出")

schtasks /Query /TN $TaskName *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "未找到任务：$TaskName" -ForegroundColor Yellow
    return
}
schtasks /Delete /TN $TaskName /F
if ($LASTEXITCODE -eq 0) { Write-Host "✅ 已删除任务：$TaskName" -ForegroundColor Green }
