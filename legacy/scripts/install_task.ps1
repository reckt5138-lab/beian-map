# 注册“青鸾项目每日导出”计划任务
# 用法：右键本文件 ->“使用 PowerShell 运行”，或在 PowerShell 里执行：
#   powershell -ExecutionPolicy Bypass -File .\install_task.ps1
# 默认每天 00:10 运行（凌晨时段），任务名可改。

param(
    [string]$TaskName = "青鸾项目每日导出",
    [string]$Time = "00:10"
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat  = Join-Path $here "run_daily.bat"

if (-not (Test-Path $bat)) { throw "找不到 run_daily.bat：$bat" }

# 先删掉同名旧任务，避免重复
schtasks /Query /TN $TaskName *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "已存在同名任务，先删除旧任务..."
    schtasks /Delete /TN $TaskName /F | Out-Null
}

Write-Host "正在创建计划任务：$TaskName（每天 $Time 运行）"
schtasks /Create /TN $TaskName /TR "`"$bat`"" /SC DAILY /ST $Time /RL HIGHEST /F

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ 计划任务创建成功" -ForegroundColor Green
    Write-Host "   任务名：$TaskName"
    Write-Host "   执行时间：每天 $Time（电脑需处于开机或唤醒状态）"
    Write-Host "   测试运行：schtasks /Run /TN `"$TaskName`""
    Write-Host "   查看状态：schtasks /Query /TN `"$TaskName`" /V /FO LIST"
    Write-Host ""
    Write-Host "提示：若希望睡眠中也能跑，可在“任务计划程序”里勾选“唤醒计算机运行此任务”。"
} else {
    Write-Host "❌ 创建失败，可能需要用管理员身份运行 PowerShell" -ForegroundColor Red
}
