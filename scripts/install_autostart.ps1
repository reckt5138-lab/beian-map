# Auto-run on logon: put a shortcut to the scheduler into the user's Startup folder.
# Free, no admin rights, works with paths that contain spaces.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1 -Uninstall
# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI when it has no BOM.
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$bat = Join-Path $here "run_scheduler.bat"
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$lnk = Join-Path $startup "QingLuan-Daily-Export.lnk"

if ($Uninstall) {
  if (Test-Path -LiteralPath $lnk) { Remove-Item -LiteralPath $lnk -Force }
  Write-Host "Removed: $lnk"
  exit 0
}

if (-not (Test-Path -LiteralPath $bat)) { throw "Not found: $bat" }
if (-not (Test-Path -LiteralPath $startup)) { New-Item -ItemType Directory -Path $startup -Force | Out-Null }

$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = $bat
$s.WorkingDirectory = $root
$s.WindowStyle = 7   # minimized
$s.Description = "QingLuan daily export + LAN map service"
$s.Save()

Write-Host "Shortcut created: $lnk"
Write-Host "It starts automatically at logon (minimized)."
Write-Host "Run once now: `"$bat`""
Write-Host "Remove: this script with -Uninstall"
