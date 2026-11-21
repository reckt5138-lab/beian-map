@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY=python"
if exist "%~dp0..\python_path.txt" set /p PY=<"%~dp0..\python_path.txt"

echo ============================================================
echo  首次部署：环境检查 - 依赖 - 账号 - 登录验证 - GitHub 部署
echo ============================================================
echo.
"%PY%" "%~dp0first_setup.py" %*
echo.
echo 按任意键关闭窗口…
pause >nul
