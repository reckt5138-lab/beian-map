@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if exist "%~dp0..\python_path.txt" set /p PY=<"%~dp0..\python_path.txt"

echo ============================================================
echo  一键更新部署：检查 - 测试 - 安全扫描 - 提交 - 推送 - 触发云端
echo ============================================================
echo.
"%PY%" "%~dp0deploy_update.py" %*
echo.
echo 按任意键关闭窗口…
pause >nul
