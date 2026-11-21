@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if exist "%~dp0..\python_path.txt" set /p PY=<"%~dp0..\python_path.txt"

echo ============================================================
echo  诊断项目：环境 / 配置 / 文件 / git / 权限
echo  报告输出到 output\logs\diagnostic_report.txt（不含密码与 Token）
echo ============================================================
echo.
"%PY%" "%~dp0maintenance.py" diagnose
echo.
echo 按任意键关闭窗口…
pause >nul
